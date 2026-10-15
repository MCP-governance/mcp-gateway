# Presidio analyzer, unmodified, with spaCy's small English pipeline instead of the
# large one. The Gateway asks only for pattern entities (e-mail, Korean RRN/phone,
# credentials, cards, IBAN, SSN - gateway/app/privacy.py); none of them uses the NER
# model, which held ~800 MB and, next to a local LLM, pushed the lab past the 7.6 GB
# WSL VM of the reference laptop (D-32). Tokenisation and context words still come
# from spaCy, as before.
FROM ghcr.io/data-privacy-stack/presidio-analyzer:2.2.364
USER root
RUN pip install --no-cache-dir \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
# The pipeline spaCy runs on every analyze call is the cost: 34 of ~40 ms for 2 KB went to the neural NER and the
# dependency parser, which nothing here uses (pattern entities only, tests/korean_pii_eval.py). Tokenizer, tagger and
# lemmatizer stay, so context words (US_SSN, cards) still raise scores: masking results were identical on every
# measured sample and an analyze call took 23 ms instead of 43 ms. A tokenizer-only pipeline takes 7 ms but loses the
# US_SSN context boost.
RUN python -c "import spacy; spacy.load('en_core_web_sm', exclude=['ner', 'parser']).to_disk('/app/nlp-lite')"
COPY nlp-small.yaml /app/presidio_analyzer/conf/nlp-small.yaml
USER 1001
ENV NLP_CONF_FILE=presidio_analyzer/conf/nlp-small.yaml
