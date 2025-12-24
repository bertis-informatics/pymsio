#!/usr/bin/env bash
set -euo pipefail

echo "[*] Installing Mono (.NET) for Ubuntu..."

# 1) 기본 패키지 업데이트 & 필요한 툴 설치
sudo apt update
sudo apt install -y dirmngr gnupg apt-transport-https ca-certificates software-properties-common

# 2) Mono 공식 GPG 키 추가
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF

# 3) Mono 공식 리포지토리 추가 (stable-focal: 20.04/22.04에서 공용으로 많이 씀)
echo "deb https://download.mono-project.com/repo/ubuntu stable-focal main" | \
  sudo tee /etc/apt/sources.list.d/mono-official-stable.list

# 4) 패키지 목록 갱신
sudo apt update

# 5) Mono 전체 설치 (런타임 + 대부분의 라이브러리)
sudo apt install -y mono-complete

# 6) 확인
echo
echo "[*] Mono version:"
mono --version || echo "Mono not found in PATH?!"

echo
echo "[*] Mono installation finished."