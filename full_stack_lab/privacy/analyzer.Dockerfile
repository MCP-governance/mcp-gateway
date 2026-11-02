# Presidio analyzer, unmodified, with spaCy's small English pipeline instead of the
# large one. The Gateway asks only for pattern entities (e-mail, Korean RRN/phone,
# credentials, cards, IBAN, SSN - gateway/app/privacy.py); none of them uses the NER
# model, which holds ~800 MB and, next to a local LLM, pushes a WSL VM past its
# memory. Tokenisation and context words still come from spaCy.
FROM ghcr.io/data-privacy-stack/presidio-analyzer:2.2.364
USER root
RUN pip install --no-cache-dir \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
# The pipeline spaCy runs on every analyze call is the cost: most of that time goes to the neural NER and the
# dependency parser, which nothing here uses (pattern entities only). Tokenizer, tagger and
# lemmatizer stay, so context words (US_SSN, cards) still raise scores. A tokenizer-only pipeline is faster but
# loses the US_SSN context boost.
RUN python -c "import spacy; spacy.load('en_core_web_sm', exclude=['ner', 'parser']).to_disk('/app/nlp-lite')"
COPY nlp-small.yaml /app/presidio_analyzer/conf/nlp-small.yaml
USER 1001
ENV NLP_CONF_FILE=presidio_analyzer/conf/nlp-small.yaml
