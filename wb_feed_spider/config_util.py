import codecs
import logging
import os
import sys
from datetime import datetime

logger = logging.getLogger("spider.config_util")


def validate_config(config):
    """验证配置是否正确"""

    # 验证filter、pic_download、video_download
    argument_list = ["filter", "pic_download", "video_download"]
    for argument in argument_list:
        if config[argument] != 0 and config[argument] != 1:
            logger.warning("%s值应为0或1,请重新输入", config[argument])
            sys.exit()

    # 验证write_mode
    write_mode = ["txt", "csv", "json", "mongo", "mysql", "sqlite", "kafka"]
    if not isinstance(config["write_mode"], list):
        logger.warning("write_mode值应为list类型")
        sys.exit()
    for mode in config["write_mode"]:
        if mode not in write_mode:
            logger.warning(
                "%s为无效模式，请从txt、csv、json、mongo、sqlite, kafka和mysql中挑选一个或多个作为write_mode",
                mode,
            )
            sys.exit()
