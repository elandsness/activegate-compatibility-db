#!/usr/bin/env python3
"""
Setup script for ActiveGate Compatibility Intelligence CLI.
"""

from setuptools import setup, find_packages
import os

# Read the contents of README file if it exists
def read_readme():
    readme_file = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

setup(
    name='activegate-compatibility',
    version='1.0.0',
    description='ActiveGate Compatibility Intelligence System',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    author='Dynatrace Solutions Engineering',
    author_email='erik.landsness@dynatrace.com',
    url='https://github.com/elandsness/activegate-compatibility-db',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'requests>=2.31.0',
        'beautifulsoup4>=4.12.2',
        'lxml>=4.9.3',
        'selenium>=4.15.2',
        'APScheduler>=3.10.4',
        'spacy>=3.7.2',
        'transformers>=4.35.2',
        'torch>=2.1.1',
        'scikit-learn>=1.3.2',
        'neo4j>=5.14.1',
        'click>=8.1.7',
        'pyyaml>=6.0.1',
    ],
    python_requires='>=3.9',
    entry_points={
        'console_scripts': [
            'agi=src.cli.main:cli',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'Topic :: System :: Monitoring',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)