"""Content-addressed raw evidence storage with forward-only Git size policy."""
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import tempfile
from thm._bounded_files import bounded_file_bytes
from thm.systems.contracts import integer, nonempty

GIT_THRESHOLD = 1024*1024
MAX_ARTIFACT = 1024*1024*1024


@dataclass(frozen=True)
class EvidenceArtifactManifest:
    sha256: str
    size: int
    mime: str
    schema: str
    source_commit: str
    producer: str
    dataset: str
    workload: str
    locator: str
    provider: str = 'local-cas'
    command: tuple[str, ...] = ()

    def __post_init__(self):
        if len(self.sha256) != 64 or any(x not in '0123456789abcdef' for x in self.sha256):
            raise ValueError('content SHA256 required')
        if len(self.source_commit) != 40 or any(x not in '0123456789abcdef' for x in self.source_commit):
            raise ValueError('source commit required')
        integer(self.size, maximum=MAX_ARTIFACT)
        for value in (self.mime, self.schema, self.producer, self.dataset, self.workload, self.locator):
            nonempty(value)
        if self.provider not in ('local-cas', 'github-artifact', 's3-compatible', 'lfs'):
            raise ValueError('unknown evidence store')

    def public(self):
        return {'manifest_schema': 'thm-evidence-artifact/1', **asdict(self),
                'normal_git_eligible': self.size <= GIT_THRESHOLD,
                'threshold_bytes': GIT_THRESHOLD, 'historical_artifacts_rewritten': False}

    def verify(self, data):
        if len(data) != self.size or hashlib.sha256(data).hexdigest() != self.sha256:
            raise ValueError('evidence consumed bytes mismatch')
        return data


class LocalEvidenceStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data):
        if not isinstance(data, bytes) or len(data) > MAX_ARTIFACT:
            raise ValueError('bounded immutable evidence bytes required')
        sha = hashlib.sha256(data).hexdigest()
        path = self.root/sha
        fd, temporary = tempfile.mkstemp(prefix='.evidence-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                if stream.write(data) != len(data):
                    raise OSError('short evidence publication')
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if bounded_file_bytes(path, len(data)) != data:
                    raise ValueError('corrupt existing CAS object')
        finally:
            os.unlink(temporary)
        return {'sha256': sha, 'size': len(data), 'locator': str(path), 'provider': 'local-cas'}

    def get(self, manifest):
        if manifest.provider != 'local-cas':
            raise ValueError('wrong evidence provider')
        # Resolve identity, never trust an external manifest path to escape the CAS.
        return manifest.verify(bounded_file_bytes(self.root/manifest.sha256, manifest.size))


@dataclass(frozen=True)
class GitHubArtifactReference:
    repository: str
    run_id: int
    artifact_id: int
    manifest: EvidenceArtifactManifest

    def public(self):
        integer(self.run_id, minimum=1)
        integer(self.artifact_id, minimum=1)
        if self.manifest.provider != 'github-artifact':
            raise ValueError('provider mismatch')
        return {**asdict(self), 'expires': 'provider-retention-policy', 'download_verified': False}


@dataclass(frozen=True)
class LfsReference:
    manifest: EvidenceArtifactManifest

    def pointer(self):
        if self.manifest.provider != 'lfs':
            raise ValueError('provider mismatch')
        return f'version https://git-lfs.github.com/spec/v1\noid sha256:{self.manifest.sha256}\nsize {self.manifest.size}\n'


class S3CompatibleEvidenceStore:
    """Explicit caller-provided client. No default cloud, credentials or downloads."""
    def __init__(self, client, bucket, prefix='thm-evidence/'):
        self.client = client
        self.bucket = nonempty(bucket)
        self.prefix = prefix

    def put(self, data):
        if not isinstance(data, bytes) or len(data) > MAX_ARTIFACT:
            raise ValueError('bounded evidence bytes required')
        sha = hashlib.sha256(data).hexdigest()
        self.client.put_object(Bucket=self.bucket, Key=self.prefix+sha, Body=data,
                               Metadata={'sha256': sha}, IfNoneMatch='*')
        return {'sha256': sha, 'size': len(data), 'provider': 's3-compatible',
                'locator': 's3://'+self.bucket+'/'+self.prefix+sha}

    def get(self, manifest):
        if manifest.provider != 's3-compatible':
            raise ValueError('provider mismatch')
        response = self.client.get_object(Bucket=self.bucket, Key=self.prefix+manifest.sha256)
        stream = response['Body']
        try:
            if response.get('ContentLength') != manifest.size:
                raise ValueError('object length mismatch')
            data = stream.read(manifest.size+1)
            return manifest.verify(data)
        finally:
            stream.close()
