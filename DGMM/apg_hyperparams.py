# training parameters
NUM_EPOCHS = 200
APG_SWEEPS = 7
SAMPLE_SIZE = 10
BATCH_SIZE = 20
LR =  5 * 1e-4

MODEL_NAME = 'apg' # options: apg | baseline-mlp | baesline-lstm
RESAMPLING_STRATEGY = 'systematic'
BLOCK_STRATEGY = 'small'
K = 4
D = 2
NUM_HIDDEN_GLOBAL = 32
NUM_HIDDEN_STATE = 32
NUM_HIDDEN_ANGLE = 32
NUM_HIDDEN_DEC = 32
NUM_NSS = 8
RECON_SIGMA =  1.5
model_params = (K, D, NUM_HIDDEN_GLOBAL, NUM_NSS, NUM_HIDDEN_STATE, NUM_HIDDEN_ANGLE, NUM_HIDDEN_DEC, RECON_SIGMA)
MODEL_VERSION = 'dgmm-%s-%s-%dsweeps-%dsamples-%.5flr' % (MODEL_NAME, RESAMPLING_STRATEGY, APG_SWEEPS, SAMPLE_SIZE, LR)
LOAD_VERSION = 'dgmm-apg-systematic-9sweeps-10samples-0.00050lr'
print('resampling:%s, block:%s, apg sweeps:%s, epochs:%s, sample size:%s, batch size:%s, learning rate:%s' % (RESAMPLING_STRATEGY, BLOCK_STRATEGY, APG_SWEEPS, NUM_EPOCHS, SAMPLE_SIZE, BATCH_SIZE, LR))
