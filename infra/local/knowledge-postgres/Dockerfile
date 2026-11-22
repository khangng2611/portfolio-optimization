# Existing application cluster is untouched. Official pgvector v0.8.1 commit pinned.
FROM postgres:17.11-bookworm@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652 AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential postgresql-server-dev-17 git ca-certificates \
    && git init /tmp/pgvector && cd /tmp/pgvector \
    && git remote add origin https://github.com/pgvector/pgvector.git \
    && git fetch --depth 1 origin 778dacf20c07caf904557a88705142631818d8cb \
    && git checkout --detach FETCH_HEAD \
    && make OPTFLAGS="" && make install
FROM postgres:17.11-bookworm@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652
COPY --from=build /usr/lib/postgresql/17/lib/vector.so /usr/lib/postgresql/17/lib/vector.so
COPY --from=build /usr/share/postgresql/17/extension/vector* /usr/share/postgresql/17/extension/
