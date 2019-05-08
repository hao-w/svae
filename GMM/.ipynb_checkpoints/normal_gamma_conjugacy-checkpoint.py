import torch
import torch.nn as nn
import torch.nn.functional as F
from normal_gamma_kls import *
from torch.distributions.normal import Normal
from torch.distributions.one_hot_categorical import OneHotCategorical as cat
from torch.distributions.gamma import Gamma
from torch import logsumexp

def params_to_nats(alpha, beta, mu, nu):
    return alpha - (1./2), - beta - (nu * (mu**2) / 2), nu * mu, - nu / 2

def nats_to_params(nat1, nat2, nat3, nat4):
    alpha = nat1 + (1./2)
    nu = -2 * nat4
    mu = nat3 / nu
    beta = - nat2 - (nu * (mu**2) / 2)
    return alpha, beta, mu, nu

def data_to_stats(obs, states, K, D):
    """
    stat1 : sum of I[z_n=k], S * B * K
    stat2 : sum of I[z_n=k]*x_n, S * B * K * D
    stat3 : sum of I[z_n=k]*x_n^2, S * B * K * D
    """
    stat1 = states.sum(2)
    states_expand = states.unsqueeze(-1).repeat(1, 1, 1, 1, D)
    obs_expand = obs.unsqueeze(-1).repeat(1, 1, 1, 1, K).transpose(-1, -2)
    stat2 = (states_expand * obs_expand).sum(2)
    stat3 = (states_expand * (obs_expand**2)).sum(2)
    return stat1, stat2, stat3

def Post_eta(obs, states, prior_alpha, prior_beta, prior_mu, prior_nu, K, D):
    stat1, stat2, stat3 = data_to_stats(obs, states, K, D)
    stat1_expand = stat1.unsqueeze(-1).repeat(1, 1, 1, D) ## S * B * K * D
    stat1_nonzero = stat1_expand
    stat1_nonzero[stat1_nonzero == 0.0] = 1.0
    x_bar = stat2 / stat1_nonzero
    post_alpha = prior_alpha + stat1_expand / 2
    post_nu = prior_nu + stat1_expand
    post_mu = (prior_mu * prior_nu + stat2) / (stat1_expand + prior_nu)
    post_beta = prior_beta + (stat3 - (stat2 ** 2) / stat1_nonzero) / 2. + (stat1_expand * prior_nu / (stat1_expand + prior_nu)) * ((x_bar - prior_nu)**2) / 2.
    return post_alpha, post_beta, post_mu, post_nu

def Post_z(obs, obs_tau, obs_mu, prior_pi, N, K):
    """
    conjugate posterior p(z | mu, tau, x) given mu, tau, x
    """
    obs_sigma = 1. / obs_tau.sqrt()
    obs_mu_expand = obs_mu.unsqueeze(-2).repeat(1, 1, 1, N, 1) # S * B * K * N * D
    obs_sigma_expand = obs_sigma.unsqueeze(-2).repeat(1, 1, 1, N, 1) # S * B * K * N * D
    obs_expand = obs.unsqueeze(2).repeat(1, 1, K, 1, 1) #  S * B * K * N * D
    log_gammas = Normal(obs_mu_expand, obs_sigma_expand).log_prob(obs_expand).sum(-1).transpose(-1, -2) + prior_pi.log() # S * B * N * K
    post_logits = F.softmax(log_gammas, dim=-1).log()
    return post_logits