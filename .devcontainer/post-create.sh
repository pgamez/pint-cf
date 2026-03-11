#!/bin/bash

# Eliminar el repositorio de Yarn que causa problemas de verificación GPG
sudo rm -f /etc/apt/sources.list.d/yarn.list

sudo apt update
sudo apt install -y vim libudunits2-dev

curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --extra dev
uv tool install prek
prek install
