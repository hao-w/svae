import torch
import torch.nn as nn
from utils import *
from normal_gamma import *
from forward_backward import *

import probtorch

def EP(models, obs, SubTrain_Params):
    """
    oneshot encoder using exact same architecture from amor-gibbs
    initialize eta
    """
    (device, sample_size, batch_size, N, K, D) = SubTrain_Params
    obs_tau, obs_mu, state, log_w_f_z, q_eta, p_eta, q_z, p_z = Init_step_eta(models, obs, N, K, D, sample_size, batch_size)
    #q_eta, p_eta, q_nu = oneshot_eta(obs, K, D)
    #log_p_eta = p_eta['means'].log_prob.sum(-1) + p_eta['precisions'].log_prob.sum(-1)
    #log_q_eta = q_eta['means'].log_prob.sum(-1) + q_eta['precisions'].log_prob.sum(-1)
    #obs_mu = q_eta['means'].value
    #obs_tau = q_eta['precisions'].value
    #q_z, p_z = enc_z.forward(obs, obs_tau, obs_mu, N, K, sample_size, batch_size)
    #log_p_z = p_z['zs'].log_prob
    #log_q_z = q_z['zs'].log_prob
    #state = q_z['zs'].value ## S * B * N * K
    #log_obs_n = Log_likelihood(obs, state, obs_tau, obs_mu, K, D, cluster_flag=False)
    #log_weights = log_obs_n.sum(-1) + log_p_z.sum(-1) - log_q_z.sum(-1) + log_p_eta.sum(-1) - log_q_eta.sum(-1)
    w_f_z = F.softmax(log_w_f_z, 0).detach()
    ## EUBO, ELBO, ESS
    eubo = (w_f_z * log_w_f_z).sum(0).mean()  ## weights S * B
    elbo = log_w_f_z.mean()
    ess = (1. / (w_f_z**2).sum(0)).mean()
    metric_step = {"eubo" : eubo, "elbo" : elbo, "ess" : ess}
    reused = (q_eta, p_eta, q_z, p_z)
    return eubo, metric_step, reused
