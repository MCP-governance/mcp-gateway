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
COPY nlp-small.yaml /app/presidio_analyzer/conf/nlp-small.yaml
USER 1001
ENV NLP_CONF_FILE=presidio_analyzer/conf/nlp-small.yaml
