import torch
from torch.distributions.normal import Normal
from torch.distributions.one_hot_categorical import OneHotCategorical as cat
import math

def shuffler(data):
    DIM1, DIM2, DIM3 = data.shape
    indices = torch.cat([torch.randperm(DIM2).unsqueeze(0) for b in range(DIM1)])
    indices_expand = indices.unsqueeze(-1).repeat(1, 1, DIM3)
    return torch.gather(data, 1, indices_expand)

def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Linear') != -1:
        m.weight.data.normal_(0.0, 1e-3)

from torch.distributions.categorical import Categorical

def resample_eta(obs_mu, radi, weights, idw_flag=True):
    S, B, K, D = obs_mu.shape
    if idw_flag: ## individual importance weight S * B * K
        ancesters_mu = Categorical(weights.permute(1, 2, 0)).sample((S, )).unsqueeze(-1).repeat(1, 1, 1, D)
        ancesters_radi = Categorical(weights.permute(1, 2, 0)).sample((S, )).unsqueeze(-1)
        obs_mu_r = torch.gather(obs_mu, 0, ancesters_mu)
        radi_r = torch.gather(radi, 0, ancesters_radi)
    else: ## joint importance weight S * B
        ancesters_mu = Categorical(weights.transpose(0,1)).sample((S, )).unsqueeze(-1).unsqueeze(-1).repeat(1, 1, K, D)
        ancesters_radi = Categorical(weights.transpose(0,1)).sample((S, )).unsqueeze(-1).unsqueeze(-1).repeat(1, 1, K, 1)
        obs_mu_r = torch.gather(obs_mu, 0, ancesters_mu)
        radi_r = torch.gather(radi, 0, ancesters_radi)
    return obs_mu_r, radi_r

def resample_mu(obs_mu, weights, idw_flag=True):
    S, B, K, D = obs_mu.shape
    if idw_flag: ## individual importance weight S * B * K
        ancesters = Categorical(weights.permute(1, 2, 0)).sample((S, )).unsqueeze(-1).repeat(1, 1, 1, D)
        obs_mu_r = torch.gather(obs_mu, 0, ancesters)
    else: ## joint importance weight S * B
        ancesters = Categorical(weights.transpose(0,1)).sample((S, )).unsqueeze(-1).unsqueeze(-1).repeat(1, 1, K, D)
        obs_mu_r = torch.gather(obs_mu, 0, ancesters)
    return obs_mu_r


def resample_state(state, weights, idw_flag=True):
    S, B, N, K = state.shape
    if idw_flag: ## individual importance weight S * B * K
        ancesters = Categorical(weights.permute(1, 2, 0)).sample((S, )).unsqueeze(-1).repeat(1, 1, 1, K) ## S * B * N * K
        state_r = torch.gather(state, 0, ancesters)
    else: ## joint importance weight S * B
        ancesters = Categorical(weights.transpose(0,1)).sample((S, )).unsqueeze(-1).unsqueeze(-1).repeat(1, 1, N, K) ## S * B * N * K
        state_r = torch.gather(state, 0, ancesters)
    return state_r

def resample(var, weights):
    dim1, _, _, dim4 = var.shape
    ancesters = Categorical(weights.permute(1, 2, 0)).sample((dim1, )).unsqueeze(-1).repeat(1, 1, 1, dim4)
    return torch.gather(var, 0, ancesters)

def True_Log_likelihood(obs, state, obs_mu, obs_rad, noise_sigma, K, D, cluster_flag=False):
    """
    cluster_flag = False : return S * B * N
    cluster_flag = True, return S * B * K
    """
    labels = state.argmax(-1)
    labels_mu = labels.unsqueeze(-1).repeat(1, 1, 1, D)
    # labels_rad = labels.unsqueeze(-1)
    obs_mu_expand = torch.gather(obs_mu, 2, labels_mu)
    distance = ((obs - obs_mu_expand)**2).sum(-1).sqrt()
    obs_dist = Normal(obs_rad, noise_sigma)
    log_distance = obs_dist.log_prob(distance) - (2*math.pi*distance).log()
    if cluster_flag:
        log_distance = torch.cat([((labels==k).float() * log_distance).sum(-1).unsqueeze(-1) for k in range(K)], -1) # S * B * K
    return log_distance

def global_to_local(var, state):
    """
    var is global variable of size S * B * K * D
    state is cluster assignment of size S * B * N * K
    """
    D = var.shape[-1]
    labels = state.argmax(-1).unsqueeze(-1).repeat(1, 1, 1, D)
    var_expand = torch.gather(var, 2, labels)
    return var_expand

def ll_angle(ob, state, angle, mu, radi, noise_sigma, cluster_flag=False):
    """
    cluster_flag = False : return S * B * N
    cluster_flag = True, return S * B * K
    """
    D = ob.shape[-1]
    K = state.shape[-1]
    # radi_expand =  global_to_local(radi, state)
    recon_mu = torch.cat((torch.cos(angle), torch.sin(angle)), -1) * radi + global_to_local(mu, state)
    p_recon = Normal(recon_mu, noise_sigma)
    log_recon = p_recon.log_prob(ob).sum(-1)
    if cluster_flag:
        log_recon = torch.cat([((labels==k).float() * log_recon).sum(-1).unsqueeze(-1) for k in range(K)], -1) # S * B * K
    return log_recon

def ss_to_stats(ss, state):
    """
    ss :  S * B * N * D
    state : S * B * N * K

    """
    D = ss.shape[-1]
    K = state.shape[-1]
    state_expand = state.unsqueeze(-1).repeat(1, 1, 1, 1, D)
    ss_expand = ss.unsqueeze(-1).repeat(1, 1, 1, 1, K).transpose(-1, -2)
    nss = (state_expand * ss_expand).sum(2)
    return nss
