# An Automatic Question Answer Generator for Japanese Texts 

This is a simple approach to automatically generate QA from Japanese texts.
No machine learning technique is used here, but for some complicated use cases, statistical methods maybe better choices.

This approach contains the following steps:
- Dependency Parsing
- Semantic Analysis (Japanese case  grammar analysis) to generate semantic labels for chunks.
- Generate QA using dependencies and semantic labels

Note that I did not implement all patterns for semantic label generation.

## memo

CaboChaを使えるようにするのが大変

https://notemite.com/python/python-cabocha-on-ubuntu/
https://noknow.info/it/os/install_cabocha_from_source?lang=ja

$ sudo apt install build-essential

$ sudo apt install mecab
$ sudo apt install libmecab-dev
$ sudo apt install mecab-ipadic


mecab-ipadic-neologd のインストール
$ cd /var/lib/mecab/dic
$ sudo git clone https://github.com/neologd/mecab-ipadic-neologd.git
$ cd mecab-ipadic-neologd
$ sudo bin/install-mecab-ipadic-neologd


CRF++-0.58のインストール

$ cd
$ wget "https://drive.google.com/uc?export=download&id=0B4y35FiV1wh7QVR6VXJ5dWExSTQ" -O CRF++-0.58.tar.gz
$ tar zxvf CRF++-0.58.tar.gz
$ cd CRF++-0.58
$ ./configure
$ make
$ sudo make install
$ sudo ldconfig
$ cd .. CRF++-0.58
$ rm -rf CRF++-0.58
$ rm CRF++-0.58.tar.gz

CaboCha-0.68のダウンロード

$ FILE_ID=0B4y35FiV1wh7SDd1Q1dUQkZQaUU
$ FILE_NAME=cabocha-0.69.tar.bz2
$ curl -sc /tmp/cookie "https://drive.google.com/uc?export=download&id=${FILE_ID}" > /dev/null
$ CODE="$(awk '/_warning_/ {print $NF}' /tmp/cookie)"  
$ curl -Lb /tmp/cookie "https://drive.google.com/uc?export=download&confirm=${CODE}&id=${FILE_ID}" -o ${FILE_NAME}

※どうも、google driveの大きすぎてウイルスチェックできないがよいか？警告で止まる印象。
直接取ってくるしか。

CaboCha-0.68のインストール

$ bzip2 -dc cabocha-0.69.tar.bz2 | tar xvf -
$ cd cabocha-0.69
$ ./configure --with-mecab-config=`which mecab-config` --with-charset=UTF8
$ make
$ make check
$ sudo make install
$ sudo ldconfig

$ cd python
$ python setup.py install
$ pip install mecab-python3

...
mecabrcの位置

mecab-ipadic-utf8 を入れてそちらの辞書を使うよう？

<pre>
>>> import CaboCha
>>> sentence = '霜降り明星（しもふりみょうじょう）は、2018年『M-1グランプリ』14代目王者。'
>>> c = CaboCha.Parser('-d /usr/lib/x86_64-linux-gnu/mecab/dic/mecab-ipadic-neologd')
>>> print(c.parseToString(sentence))
        霜降り明星-----D      
              （しも-D |      
                  ふり-D      
      みょうじょう）は、-----D
                    2018年-D |
           『M-1グランプリ』-D
                  14代目王者。
EOS
</pre>