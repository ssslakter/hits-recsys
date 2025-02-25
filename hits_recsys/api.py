# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/02_api.ipynb.

# %% auto 0
__all__ = ['DEF_FMT', 'MODEL_CLASS', 'init_logger', 'LoggingQueue', 'cli', 'PredictRequest', 'add_routes', 'add_logging', 'serve']

# %% ../nbs/02_api.ipynb 3
from collections import deque
import logging as l
from fastcore.all import *
from .collab import *
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from importlib import metadata
import uvicorn
from datetime import date
from .embed import EmbedAdapter

# %% ../nbs/02_api.ipynb 5
DEF_FMT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def init_logger(name: str = None, level=l.INFO, format: str = None, handlers: list = None, logs_dir='./logs'):
    '''Initializes a logger, adds handlers and sets the format. If logs_dir is provided, a file handler is added to the logger.'''
    handlers = ifnone(handlers, [])
    handlers.append(l.StreamHandler())
    if logs_dir: 
        p = Path(logs_dir)/f'{date.today()}.log'
        p.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(l.FileHandler(p)) 
    log_fmt = l.Formatter(ifnone(format, DEF_FMT), datefmt='%Y-%m-%d %H:%M:%S')
    log = l.getLogger(name)
    log.setLevel(level)
    log.handlers.clear()
    for h in handlers: h.setFormatter(log_fmt); log.addHandler(h)

# %% ../nbs/02_api.ipynb 6
class LoggingQueue(deque):
    '''deque with `logging.Handler` api methods'''
    def put_nowait(self, rec): self.append(rec.message)

# %% ../nbs/02_api.ipynb 11
MODEL_CLASS ={'collab': CollabUserBased, 'embed': EmbedAdapter}

@call_parse
def cli(optype, # operation to peroform, one of 'train', 'eval' or 'pred'
        r_path, # path to dataset with ratings
        m_path,  # path to dataset with movie titles
        model_type: str = 'collab', # type of model to train, one of `collab`, `embed`
        model: Path=None, # path to model if not train
        out: Path = './models'):  # folder for output model, by default will save to './models'
    
    assert optype in ['train','eval','pred'], 'incorrect operation type'
    init_logger()
    
    if model: 
        l.info(f"Loading model from {model}")
        serv = ModelService.load(model, MODEL_CLASS[model_type]())
    
    l.info(f"loading datasets from {r_path} and {m_path}")
    ds = TfmdDataset(read_movielens(r_path,m_path))
    l.info(f"datasets loaded")

    l.info(f"start operation: {optype}")
    if optype=='train':
        serv = ModelService(MODEL_CLASS[model_type](), ds)
        serv.train()
        l.info(f"model trained")
        serv.save(out)
        l.info(f"model saved to {out}")
    elif not serv.model:
        l.error("You are trying to run model without providing correct model path")
    if optype=='eval':
        loss = serv.eval(ds)
        l.info(f"loss = {loss.item()}")
    if optype=='pred':
        res = serv.pred(ds)
        with open(out, 'w') as f:
            f.writelines([f"{line}\n" for line in res])
        l.info(f"preds are saved to {out}")

# %% ../nbs/02_api.ipynb 17
class PredictRequest(BaseModel):
    '''Request for prediction'''
    movie_names: list
    ratings: list

# %% ../nbs/02_api.ipynb 18
def add_routes(app, serv):
    @app.get("/api/predict")
    async def predict(body: PredictRequest):
        if max(body.ratings) > 5 or min(body.ratings) < 0: 
            raise HTTPException(400, f"Ratings not in correct ranges")
        if len(body.ratings) != len(body.movie_names):  
            raise HTTPException(400, f"Not correct number of ratings")
        try:
            return serv.recommend(body.movie_names, body.ratings, 20)
        except KeyError as e:
            raise HTTPException(400, f"Movie {e.args[0]} not found")

    @app.post("/api/reload")
    async def reload(): 
        serv.load(app.location, app.model_cls())
        l.info("model reloaded")

    @app.get("/api/similar")
    async def similar(movie_name: str):
        l.info(f"getting similar movies to {movie_name}")
        try:
            return serv.similar_movies(movie_name)
        except KeyError:
            raise HTTPException(404, f"Movie {movie_name} not found")
    
    @app.get("/api/movies")
    async def movies(prefix:str, page:int=0):
        l = [m for m in serv.ds.movie_map if m.startswith(prefix)]
        return l[min(20*page,len(l)):min(20*(page+1),len(l))]
    
    @app.get("/api/info")
    async def info():
        return dict(metadata.metadata('hits-recsys'))

# %% ../nbs/02_api.ipynb 19
def add_logging(app, q): 
    @app.get("/api/log")
    async def log(page: int = -1, n_logs: int = 20):
        logs = list(q)
        tail = (page+1)*n_logs
        return {'logs': logs[max(page*n_logs,-len(logs)) : None if tail<=0 else tail]}

# %% ../nbs/02_api.ipynb 20
@call_parse
def serve(host='127.0.0.1',
          port=5000, # port to listen on
          model_type: str = 'collab', # type of model to train, one of `collab`, `embed`
          model_dir='./models', # directory to load model from
          logs_dir='./logs'): # logs directory
    
    q = LoggingQueue([], 20)
    init_logger(handlers=[l.handlers.QueueHandler(q)], logs_dir=logs_dir)
    app = FastAPI()
    app.location = model_dir
    app.model_cls = MODEL_CLASS[model_type]
    serv = ModelService.load(model_dir, app.model_cls())
    if not serv.model: 
          l.error("You are trying to run model without providing correct model path! Shutting down...")
          return
    add_routes(app, serv)
    add_logging(app,q)
    serv.save(model_dir)
    if in_notebook(): 
          import nest_asyncio
          nest_asyncio.apply()
    cfg = uvicorn.Config(app, host=host, port=port, log_config=None)
    server = uvicorn.Server(cfg)
    server.run()
