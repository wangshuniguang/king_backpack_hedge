#!/usr/bin/env python

import os
import logging
from logging.handlers import RotatingFileHandler


def setup_logger(log_name):
    logger = logging.getLogger('backpack')
    logger.setLevel(logging.INFO)

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_filepath = os.path.join(logs_dir, f'{log_name}.log',)

    # 创建文件handler，限制单个文件大小为100MB，保留3个备份
    file_handler = RotatingFileHandler(log_filepath, maxBytes=100 * 1024 * 1024, backupCount=3)
    file_handler.setLevel(logging.INFO)
    # 创建日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
