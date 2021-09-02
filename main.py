import argparse
import os
import time
import timeit

import pandas as pd
import torch
import transformers  # Requires sentencepiece
import yaml
from functools import partial

from metrics import gather_metrics
from utils import _get_logger

NAME2MODEL = {
   "bert": [transformers.BertModel, transformers.BertTokenizer, "bert-base-uncased"],
   "roberta": [
       transformers.RobertaModel,
       transformers.RobertaTokenizer,
       "roberta-base",
   ],
   "deberta": [
       transformers.DebertaModel,
       transformers.DebertaTokenizer,
       "microsoft/deberta-base",
   ],
   "distilbert": [
       transformers.DistilBertModel,
       transformers.DistilBertTokenizer,
       "distilbert-base-uncased",
   ],
    "funnel_transformer": [
        transformers.FunnelModel,
        transformers.FunnelTokenizer,
        "funnel-transformer/small",
    ],
   "ibert": [
       transformers.IBertModel,
       transformers.RobertaTokenizer,
       "kssteven/ibert-roberta-base",
   ],
    "albert": [
        transformers.AlbertModel,
        transformers.AlbertTokenizer,
        "albert-base-v2",
    ],
    "longformer": [
        transformers.LongformerModel,
        transformers.LongformerTokenizer,
        "allenai/longformer-base-4096",
    ],
    "mobile_bert": [
        transformers.MobileBertModel,
        transformers.MobileBertTokenizer,
        "google/mobilebert-uncased",
    ],
    "reformer": [
        transformers.ReformerModel,
        transformers.ReformerTokenizer,
        "google/reformer-enwik8",
    ],
    "squeeze_bert": [
        transformers.SqueezeBertModel,
        transformers.SqueezeBertTokenizer,
        "squeezebert/squeezebert-uncased",
    ],
}


def main(opts, device, model_name, metrics, results_dir, logger):
    results_fname = f"{results_dir}/{device}.csv"
    dataframe = (
        pd.read_csv(results_fname) if os.path.exists(results_fname) else pd.DataFrame()
    )

    # Load Model & Tokenizer
    logger.info(f"Loading {model_name} model.")
    model_fn, tokenizer_fn, checkpoint = NAME2MODEL[model_name]
    tkr = tokenizer_fn.from_pretrained(checkpoint)
    model = model_fn.from_pretrained(checkpoint)
    model.requires_grad_(opts["requires_grad"])
    if not opts['requires_grad']:
        model.eval()

    # Set CUDA Devices
    if opts["use_cuda"]:
        model.to("cuda")
        device = torch.device(f"{opts['device']}:{opts['device_idx']}")
    else:
        device = torch.device("cpu")

    MIN_LENGTH = 3 if model_name == "funnel_transformer" else 0  # Min Length: 1
    MAX_LENGTH = 10  # Max Length: 512

    seq_lengths = [2 ** seq for seq in range(MIN_LENGTH, MAX_LENGTH)]  # Eval lengths from 1 to 512
    for batch_size in opts['batch_size']:
        for seq_len in seq_lengths:
            data = {
                "device": device,
                "model": model_name,
                "accelerator": opts["use_cuda"],
                "requires_grad": opts['requires_grad'],
                "batch_size": batch_size,
                "sequence_length": seq_len,
            }

            id_constructor = partial(torch.randint, low=0, high=tkr.vocab_size,
                                     size=(batch_size, seq_len), device=device)

            results = gather_metrics(opts, model, id_constructor, metrics, logger)

            # Combine the run params with the observed metrics
            data.update(results)
            dataframe = dataframe.append(data, ignore_index=True)

    del model
    dataframe.to_csv(results_fname, index=False)
    torch.cuda.empty_cache()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_file", type=str)
    parser.add_argument("--results_dir", type=str)  # experiments/MMDDYY_name/
    parser.add_argument("--device", type=str)
    parser.add_argument("--model", type=str)
    parser.add_argument(
        "--metrics", choices=["wallclock", "flops", "memory", "params"], nargs="+",
        default=["wallclock", "flops", "memory", "params"]
    )
    args = parser.parse_args()
    logger = _get_logger(args.results_dir, args.device)

    # Load config
    with open(args.config_file, "r") as config_file:
        params = yaml.safe_load(config_file)

    if args.model == "all":
        for model in NAME2MODEL.keys():
            main(params, args.device, model, args.metrics, args.results_dir, logger)
    else:
        main(params, args.device, args.model, args.metrics, args.results_dir, logger)

