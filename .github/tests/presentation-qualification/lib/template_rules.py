"""Shared static-rule constants for fixture files. The unit tests assert these
rules against the checked-in fixture sources; the runtime build re-asserts the
rendered equivalents inside the gateway image (render_check.py)."""

import re

WORKER_IMAGE_PLACEHOLDER = "__PPTX_QUAL_WORKER_IMAGE__"
GATEWAY_IMAGE_PLACEHOLDER = "__GATEWAY_IMAGE__"
TOKEN_PLACEHOLDER = "__PQ_TOKEN__"

KERNEL_NAMESPACE = "pptx-jobs"
KERNEL_SERVICE_ACCOUNT = "pptx-worker"
GATEWAY_SERVICE_ACCOUNT = "pptx-gateway"

# Upstream launch_kubernetes.py (EG 0344929cbca688440ba1bc8f5faa074fe54bd595)
# maps only KERNEL_* env vars to Jinja keywords; PORT_RANGE/PUBLIC_KEY/
# RESPONSE_ADDRESS reach the pod via extend_pod_env after rendering, so the
# template deliberately uses only kernel_id.
ALLOWED_TEMPLATE_VARS = {"kernel_id"}

KERNEL_ENV_EXPECTED = {
    "KERNEL_ID",
    "LOG_LEVEL",
    "EG_LOG_LEVEL",
    "HOME",
    "TMPDIR",
}

GATEWAY_ENV_EXPECTED = {
    "EG_AUTH_TOKEN",
    "EG_NAMESPACE",
    "EG_DEFAULT_KERNEL_SERVICE_ACCOUNT_NAME",
    "HOME",
    "JUPYTER_RUNTIME_DIR",
}

KERNEL_REQUIRED_LITERALS = [
    "namespace: pptx-jobs",
    "automountServiceAccountToken: false",
    "serviceAccountName: pptx-worker",
    "restartPolicy: Never",
    "component: kernel",
    "runAsUser: 1000",
    "runAsGroup: 1000",
    "fsGroup: 1000",
    "type: RuntimeDefault",
    "allowPrivilegeEscalation: false",
    "readOnlyRootFilesystem: true",
    "imagePullPolicy: IfNotPresent",
    "image: " + WORKER_IMAGE_PLACEHOLDER,
    "launch_ipykernel.py",
    "--cluster-type none",
    '"$KERNEL_ID"',
    '"$PUBLIC_KEY"',
    '"$RESPONSE_ADDRESS"',
    '"$PORT_RANGE"',
]

KERNEL_FORBIDDEN_SUBSTRINGS = [
    "hostPath",
    "valueFrom",
    "secretKeyRef",
    "envFrom",
    "persistentVolumeClaim",
    "configMap",
    "privileged: true",
]

ENV_NAME_LINE_RE = re.compile(r"^\s*-\s*name:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")
ENV_SECTION_HEADER_RE = re.compile(r"^(\s*)env:\s*$")
JINJA_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
VERBS_RE = re.compile(r"verbs:\s*\[(.*?)\]")
RESOURCES_RE = re.compile(r"resources:\s*\[(.*?)\]")

# Applied to kernel pod env NAMES only (never values). PUBLIC_KEY is the
# launcher's RSA public half and is name-allowed; nothing token/secret-shaped
# may appear among kernel pod env names.
FORBIDDEN_ENV_NAME_RE = re.compile(
    r"(?i)(token|secret|password|passphrase|credential|privatekey|private_key|apikey|api_key)"
)


def env_section_names(text):
    """Return the list of env-name lists, one per `env:` block, scoped by
    indentation so container/volume `- name:` lines are not conflated with
    environment entries."""
    sections = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        header = ENV_SECTION_HEADER_RE.match(lines[i])
        if not header:
            i += 1
            continue
        indent = len(header.group(1))
        names = []
        j = i + 1
        while j < len(lines):
            line = lines[j]
            if not line.strip():
                j += 1
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= indent:
                break
            match = ENV_NAME_LINE_RE.match(line)
            if match:
                names.append(match.group(1))
            j += 1
        sections.append(names)
        i = j
    return sections


def env_names(text):
    return [name for section in env_section_names(text) for name in section]


def jinja_vars(text):
    return set(JINJA_VAR_RE.findall(text))


def strip_comments(text):
    """Drop whole-line comments so content assertions check real YAML/JSON
    payload rather than rationale comments (which legitimately mention words
    like secrets)."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def replace_worker_image(text, image):
    if WORKER_IMAGE_PLACEHOLDER not in text:
        raise ValueError("worker image placeholder missing")
    rendered = text.replace(WORKER_IMAGE_PLACEHOLDER, image)
    if WORKER_IMAGE_PLACEHOLDER in rendered:
        raise ValueError("worker image placeholder not fully replaced")
    return rendered
