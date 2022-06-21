# -*- coding: utf-8 -*-

import os
import json
import requests
import pickle
import numpy as np

import spacy
import ginza

from operator import itemgetter
import copy

def spacy_cabocha_chunk_parser(doc):
    # json に落とし込む
    jsonfile=doc.to_json()

    # トークンID
    for tok in jsonfile['tokens']:
        tok['@id'] = str(tok['id'])

    # 品詞詳細を分解 (品詞, 品詞細分類1, 品詞細分類2, 品詞細分類3)
    for tok in jsonfile['tokens']:
        feature = tok['tag']
        tok['@feature'] = [ feature.split('-')[i] if i < len(feature.split('-')) else '*' for i in range(4)]

    # 活用形, 活用型 (inflection)
    for tok, token in zip(jsonfile['tokens'], doc):
        morph = token.morph.to_dict()['Reading']

        try:
            inflection = token.morph.to_dict()['Inflection'].split(';')[::-1]
        except:
            inflection = ['*', '*']

        tok['@feature'] += inflection

    # 原形, 読み, 発音
    for tok, token in zip(jsonfile['tokens'], doc):
        morph = token.morph.to_dict()['Reading']
        lemma = token.lemma_

        tok['@feature'] += [lemma, morph, morph]

    for tok in jsonfile['tokens']:
        tok['@feature'] = ','.join(tok['@feature'])


    # テキスト(reading_form)
    for tok, token in zip(jsonfile['tokens'], doc):
        tok['#text'] = token.orth_

    # 固有表現
    for tok, token in zip(jsonfile['tokens'], doc):
        if token.ent_iob_ == 'B':
            tok['@ne'] = f'B-{token.ent_type_}'.upper()
        elif token.ent_iob_ == 'I':
            tok['@ne'] = f'I-{token.ent_type_}'.upper()
        else:   # 'O'
            tok['@ne'] = 'O'

    # 文節係り受け情報
    ## chunk = 文節とみなす
    bunsetu_head_tokens = ginza.bunsetu_head_tokens(doc)    # 文節ヘッド
    bunsetu_head_list = [tok.i for tok in bunsetu_head_tokens]  # 文節ヘッドのトークンID
    link_head_list = [ tok.head.i for tok in bunsetu_head_tokens]   # 文節ヘッドの親(=かかり先)のトークンID

    ## 0スタートで詰める
    chunk_id_list = list(range(len(bunsetu_head_list)))
    conv_idx = dict()
    for id, i in zip(bunsetu_head_list, chunk_id_list):
        conv_idx[id] = i
    link_id_list = [conv_idx[id] for id in link_head_list]

    ## 根では自己参照のため -1
    link_id_list = [ (j if i != j else -1) for i, j in zip(chunk_id_list, link_id_list)]


    # 文節情報が入っていないので追加
    # chunk 相当のspanとして。
    bunsetu_spans = [ {'start': bs.start, 'end': bs.end} for bs in ginza.bunsetu_spans(doc)]

    ## chunk_id, link_id, tok を設定
    for chunk, chunk_id, link_id in zip(bunsetu_spans, chunk_id_list, link_id_list):
        chunk['@id'] = str(chunk_id)
        chunk['@link'] = str(link_id)
        chunk['@rel'] = 'D' # dummy
        chunk['@score'] = str(-1.0)  # dummy
        chunk['@head'] = str(0) # dummy
        chunk['@func'] = str(1) # dummy
        chunk["tok"] = jsonfile['tokens'][chunk['start']:chunk['end']]

    ## 互換性を維持する配置
    jsonfile["sentence"] = {'chunk': bunsetu_spans}

    return jsonfile

class QAGeneration:
    def __init__(self):
        # 初期化

        self.parsed_sentence = None
        # extract from node_list
        self.dependencies = list()
        self.chunkid2text = dict()

        self.spacy_parser = spacy.load('ja_ginza')

    def _set_head_form(self, node_map):

        for chunk_id, node in node_map.items():
            tags = node["tag"]
            num_morphs = len(tags)
            # extract bhead (主辞) and bform (語形) from a chunk
            bhead = -1
            bform = -1
            for i in range(num_morphs-1, -1, -1):
                if tags[i][0] == u"記号":
                    continue
                else:
                    if bform == -1: bform = i
                    if not (tags[i][0] == u"助詞"
                        or (tags[i][0] == u"動詞" and tags[i][1] == u"非自立")
                        or tags[i][0] == u"助動詞"):
                        if bhead == -1: bhead = i

            node['bhead'] = bhead
            node['bform'] = bform

            node_map[chunk_id] = node

        return node_map

    def parse(self, doc):
 
        tree = self.spacy_parser(doc)
        #xml_dict = spacy_chunk_parser(tree)
        xml_dict = spacy_cabocha_chunk_parser(tree)
        return xml_dict, True

    def _is_yogen(self, node):
        bhead_tag = node['tag'][node['bhead']]
        bform_tag = node['tag'][node['bform']]

        if bhead_tag[0] == u"動詞":
            return True, u"動詞"
        elif bhead_tag[0] == u"形容詞":
            return True, u"形容詞"
        # elif bhead_tag[1] == u"形容動詞語幹":
        elif bhead_tag[0] == u"形状詞":    # spacy/GiNZAではこれで代用?
            return True, u"形容詞"
        elif bhead_tag[0] == u"名詞" and bform_tag[0] == u"助動詞":
            return True, u"名詞_助動詞"
        else:
            return False, u""

    def _is_case(self, node):
        # 用言の直前の形態素が格かどうかを判定する
        # 格である場合は、格の直前の形態素の意味を解析する（time（7時に）かplace（公園で遊ぶ）かagent（私が動詞）か）
        bhead_tag = node['tag'][node['bhead']]
        bform_tag = node['tag'][node['bform']]
        bform_surface = bform_tag[-1]
        if (bform_tag[0] == u"助詞" and bform_tag[1] == u"格助詞"
            and (bform_surface in set([u"ガ", u"ヲ", u"ニ", u"ト", u"デ", u"カラ", u"ヨリ", u"ヘ", u"マデ"]))):
            
            if bhead_tag[1] == u"代名詞" \
                or bhead_tag[0] == u"代名詞" \
                or (bhead_tag[0] == u"名詞" and bhead_tag[1] == u"接尾"):
                # 代名詞加算
                return True, "agent"
            elif bform_surface == u"ニ" and \
                (node['ne'][node['bhead']] == u"B-DATE" or \
                    (bhead_tag[1] == u"接尾" and bhead_tag[-1] == u"ジ")):
                #  「９時に」の場合、時は時間の固有名詞として認識されないようなので、featureに「ジ」があれば時間として扱う
                # time
                return True, "time"
            elif bform_surface == u"デ" and \
                (node['ne'][node['bhead']] == u"B-LOCATION" or bhead_tag[0] == u"名詞"):
                # place
                return True, "place"
            else:
                return True, bform_surface
        elif bhead_tag[0] == u"名詞" and bform_tag[0:2] == [u"名詞", u"接尾"]:
            return True, u"名詞接尾"
        else:
            return False, u""

    def _extract_case_frame(self, node_map):
        # 深層格解析
        for chunk_id, node in node_map.items():

            is_yogen, yogen = self._is_yogen(node)
            if is_yogen:
                for case_cand in [node_map[child_id] for child_id in node['deps']]:
                    is_case, case = self._is_case(case_cand)
                    #print("is_case, case, yogen:", is_case, case, yogen)
                    if is_case:
                        # 格（ガ格、ヲ格、ニ格、ト格、デ格、カラ格、ヨリ格、ヘ格、マデ格、無格）＋用言（動詞、形容詞、名詞＋判定詞）形式の文節に意味役割を生成
                        # 全組み合わせに変換対応は難しいが、固定でいくつか対応します。
                        # ex. が綺麗（ガ格＋形容詞）→how is

                        meaning_label = ""

                        if case == u"ガ" and yogen == u"形容詞":
                            # 属性を持つ対象	<aobject>花</aobject>が<pred>きれい</pred>
                            meaning_label = "aobject"
                        elif case == u"agent" or case == u"time" or case == u"place":
                            meaning_label = case
                        else:
                            pass

                        #print("meaning_label", meaning_label)

                        case_cand["meaning_label"] = meaning_label
        return node_map

    def _extract_dependencies(self, jsonfile):
        # 解析結果(json)から係り受け情報を抽出

        chunkid2text = dict() # (chunk_id: joined_tokens)
        
        # map of chunks
        node_map = {}
        for chunk in jsonfile["sentence"]["chunk"]:

            if chunk == "@id" or chunk == "@link" \
                or chunk == "@rel" or chunk == "@score" \
                or chunk == "@head" or chunk == "@func" or chunk == "tok":
                continue

            chunk_id = int(chunk["@id"])
            if isinstance(chunk["tok"], list):
                # #textが取れない場合があるので、取れるtokenのみからlistを作る
                tokens = [token["#text"] for token in chunk["tok"] if "#text" in token]
                tokens_feature = [token["@feature"] for token in chunk["tok"]]
                # named entity
                # @neが取れない場合があるらしいので、取れるtokenのみからlistを作る
                # tokens_ne = [token["@ne"] for token in chunk["tok"]]
                tokens_ne = [token["@ne"] for token in chunk["tok"] if "@ne" in token]
            else:
                if "#text" not in chunk["tok"]:
                    continue
                tokens = [chunk["tok"]["#text"]]
                tokens_feature = [chunk["tok"]["@feature"]]
                tokens_ne = [chunk["tok"]["@ne"]] if "@ne" in chunk["tok"] else []

            joined_tokens = "".join(tokens)
            
            chunkid2text[chunk_id] = joined_tokens

            link_id = int(chunk["@link"])
            
            words = tokens
            tags = [feature.split(",") for feature in tokens_feature]
            nes = tokens_ne

            if chunk_id in node_map:
                deps = node_map[chunk_id]["deps"]
                node_map[chunk_id] = {"word": words, "tag": tags, "ne": nes, "deps":deps, "meaning_label":""}
            else:
                node_map[chunk_id] = {"word": words, "tag": tags, "ne": nes, "deps":[], "meaning_label":""}

            # 親chunkがある場合、親chunkのdeps配列にこのchunk_idを追加する
            parent_id = link_id

            if parent_id in node_map:
                parent_node = node_map[parent_id]
                parent_node["deps"].append(chunk_id)
            elif parent_id == -1:
                pass
            else:
                deps = [chunk_id]
                node_map[parent_id] = {"deps":deps}                

        return chunkid2text, node_map

    def _TorF_id_in_subtree_root_id(self,id,subtree_root_id):
        checklist = [item for item in self.dependencies if item[0]==subtree_root_id]
        if id in [item[1] for item in checklist]:
            return True
        else:
            for p,c,_ in checklist:
                if c in [item[0] for item in self.dependencies]:
                    return self._TorF_id_in_subtree_root_id(id,c)
            return False

    def _get_subtree_texts(self,subtree_root_id):
        parent_ids = [item[0] for item in self.dependencies]
        if subtree_root_id not in parent_ids:
            return self.chunkid2text[subtree_root_id]
        else:
            text = ''
            for item in self.dependencies:
                if item[0]!=subtree_root_id:continue
                text += self._get_subtree_texts(item[1])
            text += self.chunkid2text[subtree_root_id]
            return text

    def _merge_dependencies_and_case_meaning(self, node_map):

        # node_mapをflatなlistに変換する

        dependencies = list() # [chunk_id, child_chunk_id, child_chunk_label]

        for chunk_id, node in node_map.items():
            for child_chunk_id in node["deps"]:
                child_chunk_label = node_map[child_chunk_id]["meaning_label"]
                dependencies.append([chunk_id, child_chunk_id, child_chunk_label])

        # dependenciesをchunk_id順でソートします。(同じchunk_idの行をまとめます)
        dependencies.sort(key=itemgetter(0))
        return dependencies

    def generate_QA(self, doc):
        # 質問を生成する

        qas = list()
        for sentence in doc.split("。"):

            if sentence == "" or sentence is None or sentence == "\n":
                continue

            self.parsed_sentence, is_succeed = self.parse(sentence)

            if not is_succeed:
                continue

            # 係り受け解析
            self.chunkid2text, node_map = self._extract_dependencies(self.parsed_sentence)

            node_map = self._set_head_form(node_map)

            # 深層格解析（文節に意味ラベルを付与する）
            node_map = self._extract_case_frame(node_map)

            self.dependencies = self._merge_dependencies_and_case_meaning(node_map)

            #print(node_map)

            qas += self._agent2what_QA()        # 誰/何が?
            qas += self._aobject_ha2what_QA()   # 「は」何?
            qas += self._time2when_QA()         # いつ
            qas += self._place2where_QA()       # どこ

            # 以降のの各サブルーチンは、下記からの転記 (権利関係は未チェック)
            # [文書からFAQを自動生成する試み - Qiita](https://qiita.com/yukihon_lab/items/5f494d1a39849071f077)
            qas += self._object_wo2what_QA()    # 何「を」
            qas += self._object_ga2what_QA()    # 何「が」
            qas += self._source2where_QA()      # どこから
            qas += self._goal_he2where_QA()     # どこ「へ」
            qas += self._goal_ni2where_QA()     # どこ「に」
            qas += self._purpose2why_QA()       # なぜ

        return qas

    def _agent2what_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='agent']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            a = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += '誰が、'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _aobject_ha2what_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='aobject' \
                               and self.chunkid2text[item[1]][-1]=='が']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += '何が、'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _time2when_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='time']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += 'いつ、'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _place2where_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='place' \
                               and self.chunkid2text[item[1]][-1]=='で']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += '何処で'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _object_wo2what_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2] == 'object' \
                               and self.chunkid2text[item[1]][-1] == 'を']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i == target_id:
                    q += '何を'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i, target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q, a])
        return question_and_answers

    def _object_ga2what_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2] == 'object' \
                               and self.chunkid2text[item[1]][-1] == 'が']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i == target_id:
                    q += '何が'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i, target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q, a])
        return question_and_answers

    def _source2where_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='source' \
                               and self.chunkid2text[item[1]][-2:]=='から']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += '何処から'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _goal_he2where_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='goal' \
                               and self.chunkid2text[item[1]][-1]=='へ']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += '何処へ'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _goal_ni2where_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='goal' \
                               and self.chunkid2text[item[1]][-1]=='に']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += '何に'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

    def _purpose2why_QA(self):
        question_and_answers = list()
        target_dependencies = [item for item in self.dependencies if item[2]=='purpose']
        for item in target_dependencies:
            target_id = item[1]
            q = ''
            for i in self.chunkid2text.keys():
            #for i in range(len(self.chunkid2text)):
                if i==target_id:
                    q += 'なぜ、'
                    a = self._get_subtree_texts(i)
                elif self._TorF_id_in_subtree_root_id(i,target_id):
                    continue
                else:
                    q += self.chunkid2text[i]
            q += 'か？'
            q = q.replace('。','')
            question_and_answers.append([q,a])
        return question_and_answers

if __name__ == "__main__":
    qa_generator = QAGeneration()

    org_txt = "外の眺めが綺麗ですね。彼が学校に行きました。今日は大学で勉強します。"
    org_txt = "外の眺めが綺麗ですね。彼が学校に行きました。今日は大学で勉強します。日本で一番高い山は富士山です。"
    print("original text:", org_txt)
    results = qa_generator.generate_QA(org_txt)

    for q,a in results:
        print(' Q : ',q)
        print(' A : ',a)
        print()
