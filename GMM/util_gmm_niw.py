import autograd.numpy as np
from autograd.numpy.linalg import inv, det
from autograd import grad
from functools import reduce
import autograd.numpy.random as npr
import matplotlib.pyplot as plt
from scipy.stats import multivariate_normal, gamma, invwishart
from scipy.special import logsumexp, digamma, loggamma
from scipy.special import gamma as gafun
from matplotlib.patches import Ellipse
from numpy.linalg import inv


def load_iris(filename):
    features = ['sepal length (cm)',
                'sepal width (cm)',
                'petal length (cm)',
                'petal width (cm)',
                'species']
    species = ['Iris-setosa',
               'Iris-versicolor',
               'Iris-virginica']

    iris_data = []
    f = open(filename, "r")
    for data in f:
        data = data.strip().split(",")
        if len(data) != 1:
            if data[4] == species[0]:
                label = 0
            elif data[4] == species[1]:
                label = 1
            else:
                label = 2
            iris_data.append(list(map(lambda x: float(x), data[0:4])) + [label])
    iris_data = np.array(iris_data)
    Y = iris_data[:,0:4]
    (N,D) = Y.shape
    return Y, N, D

def plot_cov_ellipse(cov, pos, nstd=2, ax=None, **kwargs):
    def eigsorted(cov):
        vals, vecs = np.linalg.eigh(cov)
        order = vals.argsort()[::-1]
        return vals[order], vecs[:,order]

    if ax is None:
        ax = plt.gca()

    vals, vecs = eigsorted(cov)
    theta = np.degrees(np.arctan2(*vecs[:,0][::-1]))

    # Width and height are "full" widths, not radius
    width, height = 2 * nstd * np.sqrt(vals)
    ellip = Ellipse(xy=pos, width=width, height=height, angle=theta, **kwargs)

    ax.add_artist(ellip)
    return ellip


def empirical_cluster(Y, N, D, K):
    # True means and covs and Z
    true_mus = np.zeros((K,D))
    true_covs = np.zeros((K,D,D))
    true_Z = np.zeros(N)

    true_mus[0] = np.mean(Y[:50],0)
    true_mus[1] = np.mean(Y[50:100],0)
    true_mus[2] = np.mean(Y[100:150],0)

    true_covs[0] = np.cov(Y[:50].T)
    true_covs[1] = np.cov(Y[50:100].T)
    true_covs[2] = np.cov(Y[100:150].T)

    true_Z[0:50] = 0
    true_Z[50:100] = 1
    true_Z[100:] = 2
    return true_mus, true_covs, true_Z

# def plot_clusters(Y, mus, covs, Z):
#     features = ['sepal length (cm)',
#             'sepal width (cm)',
#             'petal length (cm)',
#             'petal width (cm)',
#             'species']
#     species = ['Iris-setosa',
#                'Iris-versicolor',
#                'Iris-virginica']
#     f, axarr = plt.subplots(4, 4, sharex='col', sharey='row',figsize=(15, 15))
#     axarr[3,0].set_xlabel('Sepal length')
#     for i in range(4):
#         axarr[3,i].set_xlabel(features[i], fontsize=15)
#         axarr[i,0].set_ylabel(features[i], fontsize=15)
#         for j in range(4):
#             if  i == j:
#                 featurei_data = np.stack((Y[:50,i],Y[50:100,i],Y[100:150,i])).T
#                 axarr[j,i].hist(featurei_data, bins=20, histtype='bar',
#                                 color=['red', 'blue', 'green'],
#                                 stacked=True, density=True)
#             else:
#                 cluster0_indices = (Z == 0)
#                 cluster1_indices = (Z == 1)
#                 cluster2_indices = (Z == 2)
#
#                 axarr[j,i].plot(Y[cluster0_indices,i],
#                                 Y[cluster0_indices,j],
#                                 'ro', mew=0.5, label=species[0][5:])
#                 axarr[j,i].plot(Y[cluster1_indices,i],
#                                 Y[cluster1_indices,j],
#                                 'bo', mew=0.5, label=species[1][5:])
#                 axarr[j,i].plot(Y[cluster2_indices,i],
#                                 Y[cluster2_indices,j],
#                                 'go', mew=0.5, label=species[2][5:])
#
#                 plot_cov_ellipse(cov=covs[0,[i,i,j,j],[i,j,i,j]].reshape(2,2),
#                                  pos=mus[0,[i,j]],
#                                  nstd=2,
#                                  ax=axarr[j,i],
#                                  color='red',
#                                  alpha=0.1)
#                 plot_cov_ellipse(cov=covs[1,[i,i,j,j],[i,j,i,j]].reshape(2,2),
#                                  pos=mus[1,[i,j]],
#                                  nstd=2,
#                                  ax=axarr[j,i],
#                                  color='blue',
#                                  alpha=0.1)
#                 plot_cov_ellipse(cov=covs[2,[i,i,j,j],[i,j,i,j]].reshape(2,2),
#                                  pos=mus[2,[i,j]],
#                                  nstd=2,
#                                  ax=axarr[j,i],
#                                  color='green',
#                                  alpha=0.1)
#
#     #f.legend(loc = 'upper right', fontsize=20)
#     plt.show()


def plot_clusters(Y, mus, covs, K):
    cmap = plt.cm.get_cmap('hsv', K)
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.plot(Y[:,0], Y[:,1], 'k.', markersize=4.0)
    for i in range(K):
        plot_cov_ellipse(cov=covs[i],
                         pos=mus[i],
                         nstd=2,
                         ax=ax,
                         color=cmap(i),
                         alpha=0.1)

    plt.show()


def quad(a, B):
    return np.dot(np.dot(a.T, B), a)

def log_expectation_wi_single(nu, W, D):
    ds = (nu + 1 - (np.arange(D) + 1)) / 2.0
    return  - D * np.log(2) + np.log(det(W)) + digamma(ds).sum()

def log_expectation_wi(nu_ks, W_ks, D, K):
    log_expectations = np.zeros(K)
    for k in range(K):
        log_expectations[k] = log_expectation_wi_single(nu_ks[k], W_ks[k], D)
    return log_expectations

def quadratic_expectation(nu_ks, W_ks, m_ks, beta_ks, Y, N, D, K):
    quadratic_expectations = np.zeros((K, N))
    for k in range(K):
        quadratic_expectations[k] = D / beta_ks[k] + nu_ks[k] * np.multiply(np.dot(Y - m_ks[k], inv(W_ks[k])), Y - m_ks[k]).sum(1)
    return quadratic_expectations.T

def log_expectations_dir(alpha_hat, K):
    log_expectations = np.zeros(K)
    sum_digamma = digamma(alpha_hat.sum())
    for k in range(K):
        log_expectations[k] = digamma(alpha_hat[k]) - sum_digamma
    return log_expectations

def vbE_step(alpha_hat, nu_ks, W_ks, m_ks, beta_ks, Y, N, D, K):
    ## return gammas_nk N by K
    quadratic_expectations = quadratic_expectation(nu_ks, W_ks, m_ks, beta_ks, Y, N, D, K)
    log_expectations_pi = log_expectations_dir(alpha_hat, K)
    log_expectation_lambda = log_expectation_wi(nu_ks, W_ks, D, K)
    log_rhos = log_expectations_pi - (D / 2) * np.log(2*np.pi) - (1 / 2) * log_expectation_lambda - (1 / 2) * quadratic_expectations

    log_gammas = (log_rhos.T - logsumexp(log_rhos, axis=1)).T
    return log_gammas

def bmm(a):
    return np.einsum('ijk,ilj->ikl', np.expand_dims(a, 1), np.expand_dims(a, 2))

def stats(log_gammas, Y, D, K):
    gammas = np.exp(log_gammas)
    N_ks = gammas.sum(0)
    Y_ks = np.zeros((K, D))
    S_ks = np.zeros((K, D, D))
    gammas_expanded = np.tile(gammas, (D, 1, 1))
    for k in range(K):
        Y_ks[k] = np.multiply(gammas_expanded[:, :, k].T, Y).sum(0) / N_ks[k]
        gammas_expanded2 = np.tile(gammas_expanded[:, :, k], (D, 1, 1))
        Y_bmm = np.swapaxes(bmm(Y - Y_ks[k]), 0, 2)
        S_ks[k] = np.multiply(gammas_expanded2, Y_bmm).sum(-1) / (N_ks[k])

    return N_ks, Y_ks, S_ks


def vbM_step(log_gammas, alpha_0, nu_0, W_0, m_0, beta_0, N_ks, Y_ks, S_ks, N, D, K):
    m_ks = np.zeros((K, D))
    W_ks = np.zeros((K, D, D))
    cov_ks = np.zeros((K, D, D))
    alpha_hat = alpha_0 + N_ks
    nu_ks = nu_0+ N_ks + 1
    beta_ks = beta_0 + N_ks

    for k in range(K):
        m_ks[k] = (beta_0 * m_0 + N_ks[k] * Y_ks[k]) / beta_ks[k]
        temp2 = Y_ks[k] - m_0
        temp2.shape = (D, 1)
        W_ks[k] = W_0 + N_ks[k] * S_ks[k] + (beta_0*N_ks[k] / (beta_0 + N_ks[k])) * np.dot(temp2, temp2.T)
        cov_ks[k] = W_ks[k] / (nu_ks[k] - D - 1)
    return alpha_hat, nu_ks, W_ks, m_ks, beta_ks, cov_ks

def log_C(alpha):
    return loggamma(alpha.sum()) - (loggamma(alpha)).sum()

def log_wishart_B(nu, W, D):
    term1 = (nu / 2) * np.log(det(W))
    term2 = - (nu * D / 2) * np.log(2)
    term3 = - (D * (D - 1) / 4) * np.log(np.pi)
    ds = (nu + 1 - (np.arange(D) + 1)) / 2.0
    term4 = - loggamma(ds).sum()
    return term1 + term2 + term3 + term4



def entropy_wishart(nu, W, D):
    term1 = log_wishart_B(nu, W, D)
    term2 = - nu * D / 2.0
    term3 = ((- nu - D - 1) / 2.0) * log_expectation_wi_single(nu, W, D)
    return term1 + term2 + term3

def kl_niw(nu_0, W_0, m_0, beta_0, nu_ks, W_ks, m_ks, beta_ks, K, S=100):
    kl_mu_lambda = 0.0
    for k in range(K):
        log_sum = 0.0
        for s in range(S):
            sigma_k = invwishart.rvs(nu_ks[k], W_ks[k])
            mu_k = multivariate_normal.rvs(m_ks[k], sigma_k / (beta_ks[k]))

            log_p_sigma_k = invwishart.logpdf(sigma_k, nu_0, W_0)
            log_p_mu_k = multivariate_normal.logpdf(mu_k, m_0, sigma_k / beta_0)

            log_q_sigma_k = invwishart.logpdf(sigma_k, nu_ks[k], W_ks[k])
            log_q_mu_k = multivariate_normal.logpdf(mu_k, m_ks[k], sigma_k / beta_ks[k])

            log_sum += log_q_sigma_k + log_q_mu_k - log_p_sigma_k - log_p_mu_k
        kl_mu_lambda += log_sum / S
    return kl_mu_lambda

def elbo(log_gammas, alpha_0, nu_0, W_0, m_0, beta_0, N_ks, Y_ks, S_ks, alpha_hat, nu_ks, W_ks, m_ks, beta_ks, Y, N, D, K):
    gammas = np.exp(log_gammas)
    log_pi_hat_ks = log_expectations_dir(alpha_hat, K)
    ## kl between pz and qz
    log_pi_hat_ks_expanded = np.tile(log_pi_hat_ks, (N, 1))
    kl_z = np.multiply(log_gammas - log_pi_hat_ks_expanded, gammas).sum()
    ## kl between p_pi and q_pi
    kl_pi = log_C(alpha_hat) - log_C(alpha_0) + np.multiply(alpha_hat - alpha_0, log_pi_hat_ks).sum()

    quad_ks = quadratic_expectation(nu_ks, W_ks, m_ks, beta_ks, Y, N, D, K)
    # log_q_mu_lambda = 0.0
    # log_p_mu_lambda_term1 = 0.0
    # log_p_mu_lambda_term2 = 0.0
    log_likelihood = 0.0
    log_likelihood2 = 0.0
    for k in range(K):

        mk_diff = m_ks[k] - m_0
        mk_diff.shape = (D, 1)
        Ykmean_diff = Y_ks[k] - m_ks[k]
        Ykmean_diff.shape = (D, 1)

        log_lambda_k_hat = log_expectation_wi_single(nu_ks[k], W_ks[k], D)
        for n in range(N):
            log_likelihood +=  - 0.5 * gammas[n, k] * (D  * np.log(2*np.pi) + log_lambda_k_hat + quad_ks[n, k])
    #     log_q_mu_lambda += (- 1 / 2) * log_lambda_k_hat + (D / 2.0) * (np.log(beta_ks[k] / (2*np.pi)) - 1.0) + entropy_wishart(nu_ks[k], W_ks[k], D)
    #     log_p_mu_lambda_term1 += (1 / 2.0) * (D * np.log(beta_0 / (2 * np.pi)) - log_lambda_k_hat - (D * beta_0 / beta_ks[k]) - (beta_0 * nu_ks[k] * quad(mk_diff, inv(W_ks[k]))))
    #     log_p_mu_lambda_term2 += log_lambda_k_hat * ((- nu_0 - D -1) / 2.0) - (1 / 2.0) * nu_ks[k] * (np.diag(np.dot(W_0, inv(W_ks[k]))).sum())
        log_likelihood2 += N_ks[k] * (- log_lambda_k_hat - (D / beta_ks[k]) - nu_ks[k] * (np.diag(np.dot(S_ks[k], inv(W_ks[k]))).sum()) - nu_ks[k] * quad(Ykmean_diff, inv(W_ks[k])) - D * np.log(2*np.pi))
    # log_p_mu_lambda = log_p_mu_lambda_term1 + log_p_mu_lambda_term2 + K * log_wishart_B(nu_0, W_0, D)
    #
    # kl_mu_lambda = log_q_mu_lambda - log_p_mu_lambda
    kl_mu_lambda = kl_niw(nu_0, W_0, m_0, beta_0, nu_ks, W_ks, m_ks, beta_ks, K, S=100)

    ##likelihood term

    log_likelihood2 *= 1 / 2
    print(log_likelihood , log_likelihood2)
    Elbo = log_likelihood - kl_z - kl_pi - kl_mu_lambda

    return Elbo
