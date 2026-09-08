"""Versioned label-free calibration workload; contains no benchmark QA/gold."""
from .identity import digest
CORPUS_VERSION=1
DOCUMENTS=[
    'Alice maintains the SQLite FTS5 index. The source document remains immutable.',
    'Bob investigated ERR_CONNECTION_RESET on the release branch version 2.3.1.',
    '北京的会议安排在五月，上海的服务器维护在六月。',
    'The cache stores exact UTF-8 encoder inputs, not authorization or memory ownership.',
    'In 2024 the engine used a sequential reference path. In 2025 batching was evaluated.',
    'La mémoire locale conserve les sources et leurs identifiants explicites.',
    'Vector dimension, normalization, quantization and device are part of execution identity. '*20,
    'Technical identifier XNG-42 is unrelated to XNG-420. Preserve exact matching.',
]
QUERIES=['SQLite source index','ERR_CONNECTION_RESET version 2.3.1','北京会议五月','exact UTF-8 cache',
         'sequential reference 2024','mémoire locale','vector normalization','XNG-42','SQLite source index']
CORPUS_SHA=digest({'version':CORPUS_VERSION,'documents':DOCUMENTS,'queries':QUERIES})

# Independent fixed performance workload: exceeds every supported document batch size.
BUILD_WORKLOAD_VERSION=1
BUILD_DOCUMENTS=[DOCUMENTS[i%len(DOCUMENTS)]+f'\nCalibration document {i}.' for i in range(512)]
BUILD_WORKLOAD_SHA=digest({'version':BUILD_WORKLOAD_VERSION,'documents':BUILD_DOCUMENTS})

QUERY_WORKLOAD_VERSION=1
BULK_QUERIES=[QUERIES[i%len(QUERIES)]+f'\nCalibration query {i}.' for i in range(128)]
QUERY_WORKLOAD_SHA=digest({'version':QUERY_WORKLOAD_VERSION,'queries':BULK_QUERIES})
