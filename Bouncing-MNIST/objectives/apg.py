import torch
import torch.nn as nn
import torch.nn.functional as F
import probtorch
from torch.distributions.normal import Normal
from torch.distributions.one_hot_categorical import OneHotCategorical as cat
from torch.distributions.categorical import Categorical

class APG():
    """
    Update z_where_t^k step by step and apply resampling after each single time step
    ========================
    conv2d usage : input 1 * SB * H * W
                 : kernels (SB) * 1 * H_k * W_k

    frames  : S * B * T * 64 * 64
    frame_t : S * B * 64 * 64
    digit : step 0  = z_what = mnist_mean                       : S * B * K * 28 * 28
            step 1:M  = dec_digit(z_what) = reconstructed mnist : S * B * K * 28 * 28
    z_where : S * B * T * K * D
    z_what : S * B * K * D
    ========================
    10.03 update : To change the sampling strategy, we merge two coor encoders because
    1. we jointly predict K*D thing even we have individual templates in the subsequent steps
    2. we break down the trajectory into each single step
    """
    def __init__(self, models, AT, K, D, T, B, S, mcmc_steps, mnist_mean, training=True):
        super().__init__()
        self.enc_coor, self.dec_coor, self.enc_digit, self.dec_digit = models
        self.AT= AT
        self.K = K
        self.D = D
        self.T = T
        self.B = B
        self.S = S
        self.mcmc_steps = mcmc_steps
        self.mnist_mean = mnist_mean.repeat(self.S, self.B, self.K, 1, 1)
        self.training = training

    def Sweeps(self, frames):
        """
        Start with the mnist_mean template,
        and iterate over z_where_t and z_what
        """
        metrics = {'phi_loss' : [], 'theta_loss' : [], 'ess' : [], 'll' : []}
        phi_loss, theta_loss, w_what, vars = self.Step0(frames, training=self.training)
        metrics['phi_loss'].append(phi_loss.unsqueeze(0))
        metrics['theta_loss'].append(theta_loss.unsqueeze(0))
        metrics['ess'].append(vars['ess'].unsqueeze(0))
        metrics['ll'].append(vars['ll'].mean().unsqueeze(0))
        # metrics['recon'].append(vars['recon'])
        for m in range(self.mcmc_steps):
            z_what = self.Resample_what(vars['z_what'], w_what)
            phi_loss_where, theta_loss_where, w_where, vars_where = self.APG_where(frames, z_what=z_what, z_where_old=vars['z_where'], training=self.training)
            phi_loss_what, theta_loss_what, w_what, vars = self.APG_what(frames, z_where=vars_where['z_where'], z_what_old=z_what, training=self.training)
            metrics['phi_loss'].append((phi_loss_what + phi_loss_where).unsqueeze(0))
            metrics['theta_loss'].append((theta_loss_what + theta_loss_where).unsqueeze(0))
            metrics['ess'].append((vars_where['ess'] + vars['ess']).unsqueeze(0) / 2)
            metrics['ll'].append(vars['ll'].mean().unsqueeze(0))
            # metrics['recon'].append(vars['recon'])
        return metrics

    def Step0(self, frames, training=True):
        vars = {'z_where' : [], 'E_where' : [], 'z_what' : [], 'E_what' : [], 'ess' : [], 'll' : []}
        for t in range(self.T):
            frame_t = frames[:,:,t, :,:]
            if t == 0:
                log_w_t, log_q_t, z_where_t, E_where_t = self.Where_1step(frame_t=frame_t, digit=self.mnist_mean, z_where_t_1=None)
                log_w_where = log_w_t
                log_q_where = log_q_t
            else:
                log_w_t, log_q_t, z_where_t, E_where_t = self.Where_1step(frame_t=frame_t, digit=self.mnist_mean, z_where_t_1=z_where_t)
                log_w_where = log_w_where + log_w_t
                log_q_where = log_q_where + log_q_t
            vars['z_where'].append(z_where_t.unsqueeze(2)) ## S * B * 1 * K * D
            vars['E_where'].append(E_where_t.unsqueeze(2))
        vars['z_where'] = torch.cat(vars['z_where'], 2)
        vars['E_where'] = torch.cat(vars['E_where'], 2).mean(0).cpu()
        cropped = self.AT.frame_to_digit_vectorized(frames, vars['z_where']).view(self.S, self.B, self.T, self.K, 28*28)
        q_f_what, p_f_what = self.enc_digit(cropped)
        vars['z_what'] = q_f_what['z_what'].value # S * B * K * z_what_dim
        vars['E_what'] = q_f_what['z_what'].dist.loc.mean(0).cpu()

        log_q_what = q_f_what['z_what'].log_prob.sum(-1).sum(-1) # S * B
        log_p_what = p_f_what['z_what'].log_prob.sum(-1).sum(-1) # S * B
        recon, ll_f = self.dec_digit.forward_vectorized(frames, vars['z_what'], z_where=vars['z_where'])
        vars['ll'] = ll_f.detach().cpu()
        vars['recon'] = recon.detach().cpu()
        log_w = ll_f.detach() + log_p_what - log_q_what + log_w_where
        w = F.softmax(log_w, 0).detach()
        vars['ess'] = (1. / (w**2).sum(0)).mean().cpu().detach()
        if training:
            phi_loss = (w * (- log_q_where - log_q_what)).sum(0).mean()
            theta_loss = (w * (-ll_f)).sum(0).mean()
            return phi_loss, theta_loss, w, vars
        else:
            return w, vars

    def Where_1step(self, frame_t, digit, z_where_t_1=None):
        frame_left = frame_t
        vars = {'log_w' : [], 'log_q' : [], 'z_where_t' : [], 'E_where_t' : []}
        for k in range(self.K):
            digit_k = digit[:,:,k,:,:]
            conved_k = F.conv2d(frame_left.view(self.S*self.B, 64, 64).unsqueeze(0), digit_k.view(self.S*self.B, 28, 28).unsqueeze(1), groups=int(self.S*self.B))
            CP = conved_k.shape[-1] # convolved output pixels ##  S * B * CP * CP
            conved_k = F.softmax(conved_k.squeeze(0).view(self.S, self.B, CP, CP).view(self.S, self.B, CP*CP), -1) ## S * B * 1639
            q_k = self.enc_coor.forward(conved_k)
            z_where_k = q_k['z_where'].value
            vars['z_where_t'].append(z_where_k.unsqueeze(2)) ## expand to S B 1 2
            log_q_f_k = q_k['z_where'].log_prob.sum(-1) ## S B D
            vars['log_q'].append(log_q_f_k.unsqueeze(-1))
            vars['E_where_t'].append(q_k['z_where'].dist.loc.mean(0).cpu().unsqueeze(1))
            if z_where_t_1 is not None:
                log_p_f_k = self.dec_coor.forward(z_where_k, z_where_t_1=z_where_t_1[:,:,k,:])
            else:
                log_p_f_k = self.dec_coor.forward(z_where_k)
            vars['log_w'].append((log_p_f_k - log_q_f_k).unsqueeze(-1)) ## S B 1
            recon_frame_t_k = self.AT.digit_to_frame(digit_k.unsqueeze(2), z_where_k.unsqueeze(2)).squeeze(2) ## S * B * 64 * 64
            frame_left = frame_left - recon_frame_t_k
        return torch.cat(vars['log_w'], -1).sum(-1), torch.cat(vars['log_q'], -1).sum(-1), torch.cat(vars['z_where_t'], 2), torch.cat(vars['E_where_t'], 2)

    def Where_apg_step(self, frame_t, digit, z_where_old_t, z_where_old_t_1=None, z_where_t_1=None):
        frame_left = frame_t
        vars = {'log_w_f' : [], 'log_w_b' : [], 'log_q' : [], 'z_where_t' : [], 'E_where_t' : []}
        for k in range(self.K):
            digit_k = digit[:,:,k,:,:]
            conved_k = F.conv2d(frame_left.view(self.S*self.B, 64, 64).unsqueeze(0), digit_k.view(self.S*self.B, 28, 28).unsqueeze(1), groups=int(self.S*self.B))
            CP = conved_k.shape[-1] # convolved output pixels ## T * S * B * CP * CP
            conved_k = F.softmax(conved_k.squeeze(0).view(self.S, self.B, CP, CP).view(self.S, self.B, CP*CP), -1) ## S * B * 1639
            q_k = self.enc_coor.forward(conved_k)
            z_where_k = q_k['z_where'].value
            vars['z_where_t'].append(z_where_k.unsqueeze(2)) ## expand to S B 1 2
            vars['E_where_t'].append(q_k['z_where'].dist.loc.mean(0).cpu().unsqueeze(1))
            log_q_f_k = q_k['z_where'].log_prob.sum(-1)
            vars['log_q'].append(log_q_f_k.unsqueeze(-1)) ## S B 1
            if z_where_t_1 is not None:
                log_p_f_k = self.dec_coor.forward(z_where_k, z_where_t_1=z_where_t_1[:,:,k,:])
            else:
                log_p_f_k = self.dec_coor.forward(z_where_k)
            ## backward
            log_q_b_k = Normal(q_k['z_where'].dist.loc, q_k['z_where'].dist.scale).log_prob(z_where_old_t[:,:,k,:]).sum(-1).detach()
            if z_where_old_t_1 is not None:
                log_p_b_k = self.dec_coor.forward(z_where_old_t[:,:,k,:], z_where_t_1=z_where_old_t_1[:,:,k,:])
            else:
                log_p_b_k = self.dec_coor.forward(z_where_old_t[:,:,k,:])

            vars['log_w_f'].append((log_p_f_k - log_q_f_k).unsqueeze(-1)) ## S B 1
            vars['log_w_b'].append((log_p_b_k - log_q_b_k).unsqueeze(-1))
            recon_frame_t_k = self.AT.digit_to_frame(digit_k.unsqueeze(2), z_where_k.unsqueeze(2)).squeeze(2) ## S * B * 64 * 64
            frame_left = frame_left - recon_frame_t_k
        return torch.cat(vars['log_w_f'], -1).sum(-1) - torch.cat(vars['log_w_b'], -1).sum(-1), torch.cat(vars['log_q'], -1).sum(-1), torch.cat(vars['z_where_t'], 2), torch.cat(vars['E_where_t'], 2)

    def APG_where(self, frames, z_what, z_where_old, training=True):
        vars = {'z_where' : [], 'E_where' : [], 'ess' : [], 'll' : []}
        Phi_loss = []
        Theta_loss = []
        for t in range(self.T):
            frame_t = frames[:,:,t, :,:]
            digit = self.dec_digit(frame_t, z_what)
            if t == 0:
                log_w_t, log_q_t, z_where_t, E_where_t = self.Where_apg_step(frame_t=frame_t, digit=digit, z_where_old_t=z_where_old[:,:,t, :, :], z_where_old_t_1=None, z_where_t_1=None)
            else:
                log_w_t, log_q_t, z_where_t, E_where_t = self.Where_apg_step(frame_t=frame_t, digit=digit, z_where_old_t=z_where_old[:,:,t, :, :],  z_where_old_t_1=z_where_old[:,:,t-1, :,:], z_where_t_1=z_where_t)

            recon_t, ll_f_t = self.dec_digit(frame_t, z_what, z_where=z_where_t)
            _, ll_b_t = self.dec_digit(frame_t, z_what, z_where=z_where_old[:,:,t,:,:])
            vars['ll'].append(ll_f_t.detach().cpu().unsqueeze(-1))
            w = F.softmax(ll_f_t - ll_b_t + log_w_t, 0).detach()
            vars['ess'].append((1. / (w**2).sum(0)).mean().cpu().unsqueeze(-1))
            z_where_t = self.Resample_where(z_where_t, w)
            vars['z_where'].append(z_where_t.unsqueeze(2))
            vars['E_where'].append(E_where_t.unsqueeze(2))
            if training:
                Phi_loss.append((w * (- log_q_t)).sum(0).mean().unsqueeze(-1))
                Theta_loss.append((w * (- ll_f_t)).sum(0).mean().unsqueeze(-1))
        vars['z_where'] = torch.cat(vars['z_where'], 2)
        vars['E_where'] = torch.cat(vars['E_where'], 2).mean(0).cpu()
        vars['ll'] = torch.cat(vars['ll'], -1).sum(-1)
        vars['ess'] = torch.cat(vars['ess'], -1).mean(-1)
        if training:
            return torch.cat(Phi_loss, -1).sum(-1), torch.cat(Theta_loss, -1).sum(-1), w, vars
        else:
            return w,  vars

    def APG_what(self, frames, z_where, z_what_old=None, training=True):
        vars = {'z_what' : [], 'E_what' : [], 'ess' : [], 'll' : [], 'recon' : []}
        croppd = self.AT.frame_to_digit_vectorized(frames, z_where).view(self.S, self.B, self.T, self.K, 28*28)
        q_f_what, p_f_what = self.enc_digit(croppd)
        z_what = q_f_what['z_what'].value # S * B * K * z_what_dim
        vars['z_what'] = z_what
        vars['E_what'] = q_f_what['z_what'].dist.loc.mean(0).cpu()
        log_q_f = q_f_what['z_what'].log_prob.sum(-1).sum(-1) # S * B
        log_p_f = p_f_what['z_what'].log_prob.sum(-1).sum(-1) # S * B
        recon, ll_f = self.dec_digit.forward_vectorized(frames, z_what, z_where=z_where)
        log_w_f = ll_f + log_p_f - log_q_f
        vars['ll'] = ll_f.cpu().detach()
        vars['recon'] = recon.cpu().detach()
        ## backward
        q_b_what, p_b_what = self.enc_digit(croppd, sampled=False, z_what_old=z_what_old)
        log_p_b = p_b_what['z_what'].log_prob.sum(-1).sum(-1).detach()
        log_q_b  = q_b_what['z_what'].log_prob.sum(-1).sum(-1).detach()
        _, ll_b = self.dec_digit.forward_vectorized(frames, z_what_old, z_where=z_where)
        log_w_b = ll_b.detach() + log_p_b - log_q_b
        w = F.softmax(log_w_f - log_w_b, 0).detach()
        vars['ess'] = (1. / (w**2).sum(0)).mean().cpu()
        if training:
            phi_loss = (w * (- log_q_f)).sum(0).mean()
            theta_loss =(w * (- ll_f)).sum(0).mean()
            return phi_loss, theta_loss, w, vars
        else:
            return w, vars


    def Resample_what(self, z_what, weights):
        S, B, K, dim4 = z_what.shape
        ancesters = Categorical(weights.transpose(0, 1)).sample((S, )).unsqueeze(-1).unsqueeze(-1).repeat(1, 1, K, dim4)
        return torch.gather(z_what, 0, ancesters)

    def Resample_where(self, z_where, weights):
        S, B, K, dim4 = z_where.shape
        ancesters = Categorical(weights.transpose(0, 1)).sample((S, )).unsqueeze(-1).unsqueeze(-1).repeat(1, 1, K, dim4) ## S * B * T * K * 2
        return torch.gather(z_where, 0, ancesters)
