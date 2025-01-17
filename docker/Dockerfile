FROM ubuntu:latest

RUN apt-get update && apt-get install -y \
    sudo \
    python3 \ 
    python3.12-venv \
    clang-15 \
    libgtk-3-dev \
    xorg \
    xvfb \
    x11-xkb-utils \
    libnss3 \
    libasound2t64

RUN groupadd -g 1100 app_user && \
    useradd -m -s /bin/bash -u 1100 -g 1100 app_user

RUN mkdir -p /opt/app && chown -R app_user:app_user /opt/app

WORKDIR /mnt
USER app_user

ENV XDG_RUNTIME_DIR=/opt/app/xdg
RUN mkdir -p $XDG_RUNTIME_DIR
RUN chmod 0700 $XDG_RUNTIME_DIR

CMD ["bash"]

# xvfb-run python -m cef_capi.smoke_test
