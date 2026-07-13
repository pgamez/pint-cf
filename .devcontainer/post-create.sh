#!/bin/bash

# Yarn repo causes GPG varification issues
sudo rm -f /etc/apt/sources.list.d/yarn.list

sudo apt update
sudo apt install -y vim libudunits2-dev plantuml

curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --group dev
uv tool install prek
prek install
