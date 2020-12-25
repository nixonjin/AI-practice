#%%
from d2l import torch as d2l
import math
import torch
import os
import random

#%%
d2l.DATA_HUB['ptb'] = (d2l.DATA_URL + 'ptb.zip',
                        '319d85e578af0cdc590547f26231e4e31cdf1e42')
def read_ptb():
    data_dir = d2l.download_extract('ptb')
    with open(os.path.join(data_dir,'ptb.train.txt')) as f:
        raw_text = f.read()
    return [line.split() for line in raw_text.split('\n')]

sentences = read_ptb()
f'# sentences: {len(sentences)}'

#%%
vocab = d2l.Vocab(sentences, min_freq=10)
f'vocab size:{len(vocab)}'
# %%
def subsampling(sentences, vocab):
    # Map low frequency words into <unk>
    sentences = [[vocab.idx_to_token[vocab[tk]] for tk in line]
                    for line in sentences]
    # Count the frequency for each word
    counter = d2l.count_corpus(sentences)
    num_tokens = sum(counter.values())

    def keep(token):
        return (random.uniform(0,1) < 
                math.sqrt(1e-4 / counter[token] * num_tokens))
    
    return [[tk for tk in line if keep(tk)] for line in sentences]

subsampled = subsampling(sentences, vocab)

#%%
d2l.set_figsize()
d2l.plt.hist([[len(line) for line in sentences],
                [len(line) for line in subsampled]])
d2l.plt.xlabel('# tokens per sentence')
d2l.plt.ylabel('count')
d2l.plt.legend(['origin','subsampled'])


# %%
def compare_counts(token):
    return (f'# of "{token}": '
            f'before={sum([line.count(token) for line in sentences])}, '
            f'after={sum([line.count(token) for line in subsampled])}')
#%%
compare_counts('the')

# compare_counts('join')
#%%
corpus = [vocab[line] for line in subsampled]
corpus[0:3]

# %%
def get_centers_and_contexts(corpus, max_window_size):
    centers, contexts = [], []
    for line in corpus:
        if len(line) < 2:
            continue
        centers += line
        for i in range(len(line)):
            window_size = random.randint(1, max_window_size)
            indices = list(range(max(0,i-max_window_size),
                                min(len(line), i+1+window_size)))
            indices.remove(i)
            contexts.append([line[idx] for idx in indices])
    return centers, contexts
#%%
all_centers, all_contexts = get_centers_and_contexts(corpus, 5)
# %%
class RandomGenerator:
    """Draw a random int in [0,n] according to n sampling weights"""
    def __init__(self, sampling_weights):
        self.population = list(range(len(sampling_weights)))
        self.sampling_weights = sampling_weights
        self.candidates = []
        self.i = 0

    def draw(self):
        if self.i == len(self.candidates):
            self.candidates = random.choices(
                self.population, self.sampling_weights, k=10000)
            self.i = 0
        self.i += 1
        return self.candidates[self.i -1]
    
# %%
def get_negatives(all_contexts, corpus, K):
    counter = d2l.count_corpus(corpus)
    sampling_weights = [counter[i]**0.75 for i in range(len(counter))]
    all_negatives, generator = [], RandomGenerator(sampling_weights)
    for contexts in all_contexts:
        negatives = []
        while len(negatives) < len(contexts) * K:
            neg = generator.draw()
            if neg not in contexts:
                negatives.append(neg)
        all_negatives.append(negatives)
    return all_negatives

all_negatives = get_negatives(all_contexts, corpus,5)
#%%
def batchify(data):
    max_len = max(len(c) + len(n) for _, c, n in data)
    centers, contexts_negatives, masks, labels = [],[],[],[]
    for center, context, negative in data:
        cur_len = len(context) + len(negative)
        centers += [center]
        contexts_negatives += [context + negative + [0] * (max_len - cur_len)]
        masks += [[1] * cur_len + [0] * (max_len - cur_len)]
        labels += [[1] * len(context) + [0] * (max_len - len(context))]
    return (d2l.reshape(torch.tensor(centers),(-1,1)), torch.tensor(contexts_negatives),\
                torch.tensor(masks), torch.tensor(labels))


def load_data_ptb(batch_size, max_window_size, num_noise_words):
    num_worders = d2l.get_dataloader_workers()
    sentences = read_ptb()
    vocab = d2l.Vocab(sentences,min_freq=10)
    subsampled = subsampling(sentences, vocab)
    corpus = [ vocab[line] for line in subsampled]
    all_centers, all_contexts = get_centers_and_contexts(corpus, max_window_size)
    all_negatives = get_negatives(all_contexts, corpus, num_noise_words)

    class PTBDataset(torch.utils.data.Dataset):
        def __init__(self, centers, contexts, negatives):
            assert len(centers) == len(contexts) == len(negatives)
            self.centers = centers
            self.contexts = contexts
            self.negatives = negatives
        
        def __getitem__(self, index):
            return (self.centers[index], self.contexts[index], self.negatives[index])
        
        def __len__(self):
            return len(self.centers)

    dataset = PTBDataset(all_centers, all_contexts, all_negatives)
    data_iter = torch.utils.data.DataLoader(dataset, batch_size,shuffle=True,
                                            collate_fn=batchify,
                                            num_worders=num_worders)
    return data_iter, vocab

#%%
data_iter,vocab = load_data_ptb(512,5,5)
for batch in data_iter:
    for name,data in zip(names, batch):
        print(name, 'shape:', data.shape)
    break
# %% pretraining word2vec

from d2l import torch as d2l
import torch
from torch import nn

batch_size, max_window_size, num_noise_words = 512, 5, 5
data_iter, vocab = d2l.load_data_ptb(batch_size, max_window_size,
                                    num_noise_words)

embed = nn.Embedding(num_embeddings=20, embedding_dim=4)
print(f'Parameter embedding_weight ({embed.weight.shape}, '
      'dtype={embed.weight.dtype})')

x = torch.tensor([[1,2,3],[4,5,6]])
embed(x)

#%%
class SigmoidBCELoss(nn.Module):
    def __init__(self):
        super().__init__()
    
    def forward(self, inputs, target, mask=None):
        out = nn.functional.binary_cross_entropy_with_logits()