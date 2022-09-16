import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="weibo-feed-spider",
    version="0.0.1",
    author="Dokudenpa",
    author_email="",
    description="爬取自己新浪微博首页内容的爬虫",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jerrylaikr/weibo-feed-spider",
    packages=setuptools.find_packages(),
    package_data={"wb_feed_spider": ["config_sample.json", "logging.conf"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    install_requires=["lxml", "requests", "tqdm", "pymongo"],
    python_requires=">=3.6",
)
