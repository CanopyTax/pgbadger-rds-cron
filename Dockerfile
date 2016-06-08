FROM canopytax/python-base

# install perl for pgbager
RUN apk add --update perl && \
    rm /var/cache/apk/*

CMD ["./run.py"]
