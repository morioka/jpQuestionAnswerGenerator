# An Automatic Question Answer Generator for Japanese Texts 

This is a simple approach to automatically generate QA from Japanese texts.
No machine learning technique is used here, but for some complicated use cases, statistical methods maybe better choices.

This approach contains the following steps:
- Dependency Parsing
- Semantic Analysis (Japanese case  grammar analysis) to generate semantic labels for chunks.
- Generate QA using dependencies and semantic labels

Note that I did not implement all patterns for semantic label generation.


## memo

fork 元のコードは、下記の記事に対応するもの。

[日本語文書からQ&Aを自動生成してみました #NLP - クリエーションライン株式会社, by 朱, 2019-05-23](https://www.creationline.com/blog/j-zhu/27771)

あるコードから派生した(/独立した?)いくつかの試みがある様子。

- [GitHub - george-j-zhu/jpQuestionAnswerGenerator: A simple automatic QA generator for Japanese texts](https://github.com/george-j-zhu/jpQuestionAnswerGenerator)
  - 上記記事のリポジトリ。このコードのfork元。依存構造解析にCaboCha を用いている。
- [文書からFAQを自動生成する試み - Qiita, by @yukihon_lab, 2018-11-20](https://qiita.com/yukihon_lab/items/5f494d1a39849071f077)
  - COTOHA-API の構文解析+深層格解析を用いている。それ以外は、上記コードと共通性が高い。

別の試みは日本語か否かを問わずある。

- [任意のテキストからクイズを作成するWebアプリを作る - Qiita, by @BuniBuni, 2021-09-18](https://qiita.com/BuniBuni/items/047aaad25ddc82c5693b)
  - spacy/GiNZAを用いて、独自コード。主語のみ対応。
- [COTOHAでクイズ自動生成 - Qiita, by @zakiyama2918, 2020-02-23](https://qiita.com/zakiyama2918/items/0329e54ef23978a60574)
  - COTOHA-APIを用いて、独自コード
- [sonoisa/deep-question-generation: 深層学習を用いたクイズ自動生成（日本語T5モデル）](https://github.com/sonoisa/deep-question-generation)
  - fork: [morioka/deep-question-generation: 深層学習を用いたクイズ自動生成（日本語T5モデル）](https://github.com/morioka/deep-question-generation)
  - t5-base-japaneseモデルを質問生成(answer-aware question generation)向けにファインチューニングしたもの
- [KristiyanVachev/Question-Generation: Generating multiple choice questions from text using Machine Learning.](https://github.com/KristiyanVachev/Question-Generation)
  - fork: [morioka/Question-Generation: Generating multiple choice questions from text using Machine Learning.](https://github.com/morioka/Question-Generation)
- [renatoviolin/Multiple-Choice-Question-Generation-T5-and-Text2Text: Question Generation using Google T5 and Text2Text](https://github.com/renatoviolin/Multiple-Choice-Question-Generation-T5-and-Text2Text)
  - fork:  [morioka/Multiple-Choice-Question-Generation-T5-and-Text2Text: Question Generation using Google T5 and Text2Text](https://github.com/morioka/Multiple-Choice-Question-Generation-T5-and-Text2Text)
- [patil-suraj/question_generation: Neural question generation using transformers](https://github.com/patil-suraj/question_generation)
  - fork: [morioka/question_generation: Neural question generation using transformers](https://github.com/morioka/question_generation)
  
### 実行例

<pre>
original text: 外の眺めが綺麗ですね。彼が学校に行きました。今日は大学で勉強します。
 Q :  何が、綺麗ですねか？
 A :  外の眺めが

 Q :  誰が、学校に行きましたか？
 A :  彼が
</pre>

### 環境準備

CaboChaを使えるよう環境設定するのが大変。~~spacyで書いた形跡があるので、そちらに振ることはできるだろう。~~ (spacy/GiNZAで書き直した。後述)

- [Ubuntu】Python の CaboCha をインストールして形態素解析を行う – notemite.com](https://notemite.com/python/python-cabocha-on-ubuntu/)
- [ソースからCaboChaをインストールする](https://noknow.info/it/os/install_cabocha_from_source?lang=ja)

```bash
$ sudo apt install build-essential

$ sudo apt install mecab
$ sudo apt install libmecab-dev
$ sudo apt install mecab-ipadic

# mecab-ipadic-neologd のインストール
$ cd /var/lib/mecab/dic
$ sudo git clone https://github.com/neologd/mecab-ipadic-neologd.git
$ cd mecab-ipadic-neologd
$ sudo bin/install-mecab-ipadic-neologd

#  CRF++-0.58のインストール
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

# CaboCha-0.68のダウンロード
$ FILE_ID=0B4y35FiV1wh7SDd1Q1dUQkZQaUU
$ FILE_NAME=cabocha-0.69.tar.bz2
$ curl -sc /tmp/cookie "https://drive.google.com/uc?export=download&id=${FILE_ID}" > /dev/null
$ CODE="$(awk '/_warning_/ {print $NF}' /tmp/cookie)"  
$ curl -Lb /tmp/cookie "https://drive.google.com/uc?export=download&confirm=${CODE}&id=${FILE_ID}" -o ${FILE_NAME}

※どうも、google driveの大きすぎてウイルスチェックできないがよいか？警告で止まる印象。直接取ってくるしか。

# CaboCha-0.68のインストール
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

mecabrcの位置...

mecab-ipadic-utf8 を入れてそちらの辞書を使うよう？
```

```python
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
```

## memo その2

MeCab + CaboCha から spacy/GiNZAに差し替えた。
本筋の処理には手を入れず、CaboCha出力に合わせるよう努めた。spacy doc の json出力には不足する項目がいくつかあり、適宜追加した。
