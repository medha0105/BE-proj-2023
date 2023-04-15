import fitz
from whoosh.index import create_in
from whoosh.fields import Schema, ID, TEXT
import codecs
import spacy
from spacy.tokens import Span
import os, os.path
import shutil
import re
import operator
import re
from django.shortcuts import render
from django.core.files import File
from whoosh.qparser import MultifieldParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from .models import Document, Sections
from .serializer import DocumentSerializer
from summarizer import Summarizer


@api_view(['POST'])
def setDocument(request):
    print("Hello", request)
    data = request.data
    print("data:", data)
    doc = Document.objects.create(
        pdf = data['pdf']
    )
    serializer = DocumentSerializer(data=doc, many=False)
    if serializer.is_valid():
        serializer.save()
    # call to preprocessing
    preprocessing()
    return Response({"Sample":"data"}) # , status=status.HTTP_500_INTERNAL_SERVER_ERROR

def preprocessing():
    l = len(Document.objects.all())
    print(Document.objects.all()[l-1])
    doc_ = Document.objects.all()[l-1]
    doc = fitz.open(doc_.pdf)
    font_counts = {}
    granularity=False

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:  # iterate through the text blocks
            if b['type'] == 0:  # block contains text
                for l in b["lines"]:  # iterate through the text lines
                    for s in l["spans"]:  # iterate through the text spans
                        if granularity:
                            identifier = "{0}_{1}_{2}_{3}".format(s['size'], s['flags'], s['font'], s['color'])
                        else:
                            identifier = "{0}".format(s['size'])
                        font_counts[identifier] = font_counts.get(identifier, 0) + 1  # count the fonts usage
    font_counts = sorted(font_counts.items(), key=operator.itemgetter(1), reverse=True)
    print("font_counts")

    if len(font_counts) < 1:
        raise ValueError("Zero discriminating fonts found!")

    p_size = float(font_counts[0][0])
    
    font_sizes = []
    for (font_size, count) in font_counts:
        font_sizes.append(float(font_size))
    font_sizes.sort(reverse=True)

    # aggregating the tags for each font size
    idx = 0
    size_tag = {}
    for size in font_sizes:
        idx += 1
        if size == p_size:
            idx = 0
            size_tag[size] = '<p>'
        if size > p_size:
            size_tag[size] = '<h{0}>'.format(idx)
        elif size < p_size:
            size_tag[size] = '<s{0}>'.format(idx)
    print("size_tag")

    pattern = re.compile("<s.>")
    header_para = []  # list with headers and paragraphs
    first = True  # boolean operator for first header
    previous_s = {}  # previous span

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:  # iterate through the text blocks
            if b['type'] == 0:  # this block contains text
                block_string = ""  # text found in block
                for l in b["lines"]:  # iterate through the text lines
                    for s in l["spans"]:  # iterate through the text spans
                        string_encode = s['text'].encode("ascii", "ignore")
                        string_decode = string_encode.decode()
                        s['text'] = string_decode
                        if s['text'].strip():  # removing whitespaces:
                            if first:
                                previous_s = s
                                first = False
                                if size_tag[s['size']]=='<p>' or pattern.match(size_tag[s['size']]): #sentence has p tag or s tag
                                    block_string = s['text']
                                elif re.compile("<h.>").match(size_tag[s['size']]):
                                    block_string = size_tag[s['size']] + s['text']
                            else:
                                if s['size'] == previous_s['size']:
                                    if block_string and all((c == "|") for c in block_string):# block_string only contains pipes
                                        if size_tag[s['size']]=='<p>' or pattern.match(size_tag[s['size']]):
                                            block_string = s['text']
                                        elif re.compile("<h.>").match(size_tag[s['size']]):
                                            block_string = size_tag[s['size']] + s['text']
                                    if block_string == "":# new block has started, so append size tag
                                        if size_tag[s['size']]=='<p>' or pattern.match(size_tag[s['size']]):
                                            block_string = s['text']
                                        elif re.compile("<h.>").match(size_tag[s['size']]):
                                            block_string = size_tag[s['size']] + s['text']
                                    else:  # in the same block, so concatenate strings
                                        block_string += " " + s['text']

                                else:
                                    if block_string != '': 
                                        header_para.append(block_string)
                                    if size_tag[s['size']]=='<p>' or pattern.match(size_tag[s['size']]):
                                        block_string = s['text']
                                    elif re.compile("<h.>").match(size_tag[s['size']]):
                                        block_string = size_tag[s['size']] + s['text']

                                previous_s = s

                if block_string != '': 
                    header_para.append(block_string)
    print("header_para")
    createSections(header_para, doc_)
            
# Extracting sections by filtering content from one heading to the next
def createSections(header_para, doc_):
    pattern = re.compile("<h.>")
    sectionStarted = False
    count=0
    fp = None
    file_name = ''
    section_names = []
    exceptionFile = 0

    for ind in range(0,len(header_para)):
        
        if pattern.match(header_para[ind][0:4]) and sectionStarted == False:
            sectionStarted = True
            file_name = (header_para[ind][4:]).strip()
            file_name = re.sub('[^a-zA-Z ]', '', file_name)
            try:
                f = open(file_name+'.txt', mode='a+')
                fp = File(f)
                section_names.append(file_name+'.txt')
                for j in range(ind+1, len(header_para)):
                    if header_para[j][0:2] != '<h':
                        count+=1
                        fp.write(header_para[j]+"\n")
                    if pattern.match(header_para[j][0:4]) and sectionStarted == True:
                        sectionStarted = False
                        if count != 0:
                            new_entry = Sections(text_file=fp, key=doc_)
                            new_entry.save()
                        fp.close()
                        path = os.path.join(os.getcwd(), file_name+'.txt')
                        os.remove(path)
                        count=0
                        ind = j-1
                        break
                    if(j == len(header_para)-1 and sectionStarted == True):
                        fp.close()
                        path = os.path.join(os.getcwd(), file_name+'.txt')
                        os.remove(path)
            except FileNotFoundError:
                print("Exception block")
                exceptionFile+=1
                f = open("DummyFileName"+str(exceptionFile)+'.txt', mode='a+',encoding='cp1252')
                fp = File(f)
                section_names.append("DummyFileName"+str(exceptionFile)+'.txt')
                for j in range(ind+1, len(header_para)):
                    if header_para[j][0:2] != '<h':
                        count+=1
                    fp.write(header_para[j]+"\n")
                    if pattern.match(header_para[j][0:4]) and sectionStarted == True:
                        sectionStarted = False
                        if count != 0:
                            new_entry = Sections(text_file=fp, key=doc_)
                            new_entry.save()
                        fp.close()
                        
                        os.remove("DummyFileName"+str(exceptionFile)+'.txt')
                        count=0
                        ind = j-1
                        break
    print("section_names")

@api_view(['POST'])
def setQuery(request):
    print(request.data)
    query = request.data["query"]
    r = request.data["summary_size"]
    print("query: ",query)
    print("range: ", r)
    ix = indexing()
    summary = parse_user_query(ix, query, r)
    return Response(summary)

def indexing():
    schema = Schema(title=TEXT(stored=True), path=ID(stored=True), content=TEXT)
    if not os.path.exists("indexdir"):
        os.mkdir("indexdir")
    ix = create_in("indexdir", schema)
    writer = ix.writer()
    l = len(Document.objects.all())
    doc_ = Document.objects.all()[l-1]

    # Retrieve sections of current document only
    t = Sections.objects.filter(key=doc_)
    for ele in t:
        f=open(str(ele.text_file),"r")
        writer.add_document(title=(str(ele)[5:]).replace('_',' '), path=u"/a", content=f.read())
    writer.commit()
    print("committed")
    return ix
    # summary = # parse_user_query(ix, query, r)
    # return summary

def parse_user_query(ix, query, r):
    print("in parse user query")
    print(query)
    sections = []
    with ix.searcher() as searcher:
        mparser = MultifieldParser(["title", "content"], ix.schema).parse(query)
        results = searcher.search(mparser, limit=None)
        for i in range(len(results)):
            sections.append(results[i]['title'])
    print("Relevant sections", sections)
    summary = summarizer(sections, r)
    return summary

def summarizer(sections, r):
    # en_nlp = spacy.load("en_core_web_sm")
    # en_nlp.add_pipe("textrank", config={ "stopwords": { "word": ["NOUN"] }})

    section_content = {}

    r1 = int(r)/100
    ratio_per_section = 3 if len(sections)>3 else len(sections)
    r1 = r1/ratio_per_section
    final_summary = ""
    count = 0
    print("brfore for")
    for sec in sections:
        print(sec)
        count += 1
        sect = "None/" + str(sec).replace(' ', '_')
        t = Sections.objects.get(text_file=sect)
        f=open(str(t.text_file),"r")
        document = f.read()
        # BERT Model
        model = Summarizer()
        result = model(document, ratio=r1)

        # Adding section content to the dict to show in the frontend as a link
        section_content[sec[:-12]] = document
        print(document)

        # TextRank
        # with codecs.open(str(t.text_file), "r") as f:
        #     document = f.read()
            # doc = en_nlp(document)
            # tr = doc._.textrank
            # for sent in tr.summary(limit_phrases=10, limit_sentences=1):

        final_summary = final_summary + str(result)
        if(count > 2):
            print("Final summary: ", final_summary)
            return {'section_content':section_content, 'summary':final_summary}
    print("Final summary: ", final_summary)
    return {'section_content':section_content, 'summary':final_summary}

@api_view(['GET'])
def getSections(request):
    l = len(Document.objects.all())
    if l==0: 
        return Response() 
    doc_ = Document.objects.all()[l-1]
    sectionNames = []
    sections = Sections.objects.filter(key=doc_)
    for section in sections:
        if "DummyFileName" in str(section):
            continue
        sectionNames.append((str(section.text_file)[5:-12]).replace('_',' '))
    return Response(sectionNames)






















    # @spacy.registry.misc("prefix_scrubber")
    # def prefix_scrubber():
    #     def scrubber_func(span: Span) -> str:
    #         while span[0].text in ("a", "the", "any"):
    #             span = span[1:]
    #         return span.text
    #     return scrubber_func
    # "scrubber": {"@misc": "prefix_scrubber"}