# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_collab.ipynb.

# %% auto 0
__all__ = ['SavePT', 'read_movielens', 'TfmdDataset', 'CollabUserBased', 'ModelService']

# %% ../nbs/01_collab.ipynb 3
from fastprogress.fastprogress import progress_bar
import pandas as pd
import numpy as np
import torch, torch.nn.functional as F
from torch import tensor
from fastai.collab import to_device, to_cpu, default_device, CategoryMap, DataLoader
from fastcore.all import *

# %% ../nbs/01_collab.ipynb 4
@patch
def pprint(l: L): print('\n'.join(l.map(str)))

class SavePT:
    '''Class to save and load PyTorch models or objects'''
    def save(self, fname: str|Path):
        '''Save the model to a file.'''
        Path(fname).parent.mkdir(parents=True,exist_ok=True)
        torch.save(self, fname)
    def load(self, fname: str|Path):
        '''Load the model from a file.'''
        obj = torch.load(fname, map_location=default_device())
        assert self.__class__ == obj.__class__, f"Class missmatch, wanted {self.__class__}, but file has {obj.__class__}"
        self.__dict__.update(obj.__dict__)

# %% ../nbs/01_collab.ipynb 8
def read_movielens(ratings_path: str, movies_path: str) -> pd.DataFrame:
    """
    Reads the MovieLens dataset from the given ratings and movies files and merges them based on the movieId.
    """
    kw1 = dict(sep='::', names=['userId', 'movieId', 'rating'], usecols=(0, 1, 2), engine='python')
    kw2 = kw1 | dict(names=['movieId', 'title'], usecols=(0, 1), encoding='ISO-8859-1')
    r, m = pd.read_csv(ratings_path, **kw1), pd.read_csv(movies_path, **kw2)
    return r.merge(m)

# %% ../nbs/01_collab.ipynb 12
class TfmdDataset(SavePT):
    '''Dataset with mapped usres and movies'''
    def __init__(self, df, movie_map = None, user_map=None):
        self.movie_map = ifnone(movie_map,CategoryMap(df.title))
        self.user_map = ifnone(user_map,CategoryMap(df.userId))
        self.xs = tensor([self.user_map.map_objs(df.userId), self.movie_map.map_objs(df.title)]).T
        if hasattr(df, 'rating'): self.ys = tensor(df.rating, dtype=torch.float32)
    def encode(self, movies): return self.movie_map.map_objs(movies)
    def decode(self, movie_ids): return self.movie_map.map_ids(movie_ids)
    def __getitem__(self,i): 
        return (self.xs[i],self.ys[i]) if hasattr(self,'ys') else (self.xs[i],)
    def __len__(self): return len(self.xs)
    @delegates(DataLoader.__init__)
    def dls(self, bs=64, **kwargs):
        '''Create a DataLoader with the given batch size'''
        return DataLoader(self, bs=bs, **kwargs)
    
    def test_ds(self, test_df): 
        '''Create a test dataset with the given DataFrame'''
        return self.__class__(test_df, self.movie_map,self.user_map)

# %% ../nbs/01_collab.ipynb 18
class CollabUserBased(SavePT):
    '''Basic model for collaborative filtering'''
    def __init__(self, device=None): 
        self.device = ifnone(device, default_device())
    
    def norm(self, x, m, std=None): 
        return (x-m)/std if std is not None else (x-m)/m
    def denorm(self, x, m, std=None): return x*std+m if std is not None else x*m+m
    
    def fit(self, ds):
        '''Fit the model to the given dataset'''
        A = to_device(torch.sparse_coo_tensor(ds.xs.T, ds.ys, dtype=torch.float32).to_dense())
        
        # little trick to use methods list nanmean and nanstd
        A[A==0] = torch.nan
        self.means = A.nanmean(dim=1)
        self.std = tensor(np.nanstd(to_cpu(A), 1), device=self.device)
        A = self.norm(A, self.means[:,None], self.std[:,None])
        # get zeros back
        A[A.isnan()] = 0
        self.A = A

    def predict(self, xb, yb=None):
        '''Predict the ratings for batch and calculate the loss if yb is given'''
        u, m = xb.T
        u, m = self.A[u], self.A[:,m].T
        # cosine similarity
        u /= u.norm(dim=1)[:,None]
        normed = (self.A/self.A.norm(dim=1)[:,None]).T
        ratings = torch.bmm((u @ normed)[:,None,:], m[...,None]).squeeze()/torch.count_nonzero(m, dim=1)**0.5
        ratings = self.denorm(ratings,  self.means[xb.T[0]], self.std[xb.T[0]])
        if yb is not None: return (ratings, F.mse_loss(ratings,yb))
        return ratings

    def recommend(self, movies: tensor, ratings: tensor, topk: int=5, filter_seen=True):
        '''Recommend topk movies based on the given ratings. \n
        If filter_seen is True, the movies that are already rated will be filtered out'''
        u = self.user_embed(movies, ratings)
        # res = self.denorm(((self.A @ u) @ self.A)/(self.A!=0).sum(0), ratings.mean()) works for ratings but not for recommendations
        res = self.denorm(((self.A @ u) @ self.A), ratings.mean())
        if not filter_seen: return res.topk(topk)
        res = res.topk(topk + len(movies))
        mask = ~torch.isin(res.indices,movies)
        return (res[0][mask][:topk], res[1][mask][:topk])

    def user_embed(self, movies: tensor, ratings: tensor):
        emb = torch.zeros(self.A.shape[-1], device=self.device)
        emb[movies] = self.norm(ratings, ratings.mean())
        return emb

    def similar_movies(self, movie_id: int, topk=5):
        '''Return topk similar movies to the given movie_id'''
        return (self.A[:,movie_id].squeeze(-1) @ self.A).topk(topk+1).indices[1:]

# %% ../nbs/01_collab.ipynb 29
class ModelService:
    '''Service class for model training, evaluation and predictions. It also provides methods for saving and loading the model.'''
    def __init__(self, model: CollabUserBased=None, ds=None):
        self.model = model
        self.ds = ds
    def _movie_enc(self, movies): 
        return tensor(self.ds.encode(movies) if isinstance(movies[0],str) else movies, device=self.model.device)
    
    def save(self, dir):
        dir = Path(dir)
        self.ds.save(dir/'ds.pt')
        self.model.save(dir/'model.pt')
    
    @classmethod
    def load(cls, dir, model):
        dir = Path(dir)
        model.load(dir/'model.pt')
        ds = torch.load(dir/'ds.pt')
        return cls(model, ds)
        
    def train(self, ds=None, model = None):
        '''Train model from scratch on dataset'''
        self.model = ifnone(model, self.model)
        ds = ifnone(ds,self.ds)
        self.model.fit(ds)
    
    def pred(self, ds=None, bs=8192):
        '''Get rating predictions for dataset'''
        dls = ifnone(ds,self.ds).dls(bs)
        preds = torch.cat([self.model.predict(*to_device(b, self.model.device))[0] for b in progress_bar(dls)])
        return preds.tolist()

    def eval(self, ds=None, bs=8192):
        '''Evaluate RMSE for dataset'''
        dls = ifnone(ds,self.ds).dls(bs)
        loss = torch.stack([self.model.predict(*to_device(b, self.model.device))[1]*len(b[0]) for b in progress_bar(dls)]).sum()
        return torch.sqrt(loss/len(ds)).item()

    def recommend(self, movies: list, ratings: list, topk=5, filter_seen=True):
        '''Recommend top k movies by user wih list of movies and ratings'''
        movies = self._movie_enc(movies)
        ratings = tensor(ratings, device=self.model.device, dtype=torch.float)
        return self.ds.decode(self.model.recommend(movies, ratings, topk, filter_seen)[1])

    def similar_movies(self, movie:str, topk=5):
        '''Find top k similar movies'''
        movie = self._movie_enc([movie])
        ms = self.model.similar_movies(movie, topk)
        return self.ds.decode(ms)
