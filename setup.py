from setuptools import setup,find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="BLOG WRITING AGENT",
    version="0.1",
    author="Himanshu Borikar",
    packages=find_packages(),
    install_requires=requirements
) 