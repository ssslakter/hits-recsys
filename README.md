# hits-recsys


<!-- WARNING: THIS FILE WAS AUTOGENERATED! DO NOT EDIT! -->

Collaborative filtration with some devops stuff

## How to

### Install

To install with pip run

``` sh
pip install https://github.com/Ssslakter/hits-recsys@main
```

### Train and evaluate

``` sh
hits-recsys_cli --help
```

``` txt
usage: hits-recsys_cli [-h] [--model_type MODEL_TYPE] [--model MODEL] [--out OUT] optype r_path m_path

positional arguments:
  optype                   operation to peroform, one of 'train', 'eval' or 'pred'
  r_path                   path to dataset with ratings
  m_path                   path to dataset with movie titles

options:
  -h, --help               show this help message and exit
  --model_type MODEL_TYPE  type of model to train, one of `collab`, `embed` (default: collab)
  --model MODEL            path to model if not train
  --out OUT                folder for output model, by default will save to './models' (default: ./models)
```

Current embedding model was trained on RTX-2060 8 epochs for about 5
minutes

## Run web-server

``` sh
hits-recsys_server --help
```

``` txt
usage: hits-recsys_server [-h] [--host HOST] [--port PORT] [--model_type MODEL_TYPE] [--model_dir MODEL_DIR] [--logs_dir LOGS_DIR]

options:
  -h, --help               show this help message and exit
  --host HOST              (default: 127.0.0.1)
  --port PORT              port to listen on (default: 5000)
  --model_type MODEL_TYPE  type of model to train, one of `collab`, `embed` (default: collab)
  --model_dir MODEL_DIR    directory to load model from (default: ./models)
  --logs_dir LOGS_DIR      logs directory (default: ./logs)
```

## Contributing

If you plan to contribute, you can install editable:

``` sh
git clone https://github.com/Ssslakter/hits-recsys
pip install -e ".[dev]"
```

## Start server in a docker container

To start with docker you can use
[docker-compose.yaml](../docker-compose.yaml) wich would build an image
and start a web-server

``` sh
git clone https://github.com/Ssslakter/hits-recsys
cd hits-recsys
docker compose up
```
