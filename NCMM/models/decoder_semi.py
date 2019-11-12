import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions.normal import Normal
import probtorch
import math
from utils import *

class Dec_x(nn.Module):
    def __init__(self, K, D, num_hidden, recon_sigma, CUDA, device):
        super(self.__class__, self).__init__()
        self.recon_mu = nn.Sequential(
            nn.Linear(1, num_hidden),
            nn.Tanh(),
            nn.Linear(num_hidden, D))
        self.recon_sigma = recon_sigma
        self.radi = torch.ones(1)
        if CUDA:
            with torch.cuda.device(device):
                self.recon_sigma = self.recon_sigma.cuda()
                self.radi = self.radi.cuda()
        # self.recon_sigma = nn.Parameter(self.recon_sigma)
        self.radi = nn.Parameter(self.radi)

    def forward(self, ob, state, angle, mu):
        p = probtorch.Trace()
        S, B, N, D = ob.shape
        # embedding = torch.cat((global_to_local(mu, state), angle), -1)
        a = self.recon_mu(angle)
        reco_centered = a / (a**2).sum(-1).unsqueeze(-1).sqrt()
        recon_mu = reco_centered * self.radi + global_to_local(mu, state)
        p.normal(recon_mu,
                 self.recon_sigma.repeat(S, B, N, D),
                 value=ob,
                 name='likelihood')

        return p