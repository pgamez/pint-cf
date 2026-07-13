#!/bin/bash

sudo apt update
sudo apt install -y vim libudunits2-dev plantuml

curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --group dev
uv tool install prek
prek install
