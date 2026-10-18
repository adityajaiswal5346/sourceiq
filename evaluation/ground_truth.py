"""
Sourciq — RAGAS Ground Truth Dataset
=======================================
Hand-curated Q&A pairs drawn exclusively from the indexed corpus:
  - pods.md       (23 vectors)
  - configmaps.md (10 vectors)

Every answer is directly attributable to a specific section in those
two documents. These are used as ground truth for RAGAS evaluation.

Metrics evaluated:
  - faithfulness:        Is the answer supported by the retrieved context?
  - answer_relevancy:    Does the answer actually address the question?
  - context_precision:   Are the retrieved chunks relevant to the question?
  - context_recall:      Does the retrieved context contain the answer?

Ground truth format:
  Each entry has:
    question:   the user query
    answer:     the ideal answer (what the system should produce)
    contexts:   the source text that supports the answer
    source:     which document it comes from
"""

GROUND_TRUTH: list[dict] = [
    # ── pods.md ───────────────────────────────────────────────────
    {
        "question": "What is a Kubernetes Pod?",
        "answer": (
            "A Pod is the smallest deployable unit in Kubernetes. "
            "It is a group of one or more containers with shared storage "
            "and network resources, and a specification for how to run the containers."
        ),
        "contexts": [
            "Pods are the smallest deployable units of computing that you can create and manage in Kubernetes. "
            "A Pod is a group of one or more containers, with shared storage and network resources, "
            "and a specification for how to run the containers."
        ],
        "source": "pods.md",
    },
    {
        "question": "What is the difference between a Pod and a container?",
        "answer": (
            "A container is an isolated process. A Pod wraps one or more containers "
            "that share network and storage. Containers in the same Pod share an IP "
            "address and port space and can reach each other via localhost."
        ),
        "contexts": [
            "A Pod (as in a pod of whales or pea pod) is a group of one or more containers, "
            "with shared storage and network resources, and a specification for how to run the containers. "
            "Containers within a Pod share an IP Address and port space, and can find each other via localhost."
        ],
        "source": "pods.md",
    },
    {
        "question": "How does Kubernetes handle init containers?",
        "answer": (
            "Init containers run before app containers in a Pod. "
            "By default, init containers run and complete before the app containers are started."
        ),
        "contexts": [
            "Some Pods have init containers as well as app containers. "
            "By default, init containers run and complete before the app containers are started."
        ],
        "source": "pods.md",
    },
    {
        "question": "What are sidecar containers in Kubernetes?",
        "answer": (
            "Sidecar containers provide auxiliary services to the main application Pod, "
            "such as a service mesh. They are kept running during the entire lifetime of the Pod."
        ),
        "contexts": [
            "You can also have sidecar containers that provide auxiliary services to the main application Pod "
            "(for example: a service mesh). "
            "Setting the Always restart policy ensures that the containers where you set it are "
            "treated as sidecars that are kept running during the entire lifetime of the Pod."
        ],
        "source": "pods.md",
    },
    {
        "question": "What is the one-container-per-Pod model in Kubernetes?",
        "answer": (
            "The one-container-per-Pod model is the most common Kubernetes use case. "
            "A Pod acts as a wrapper around a single container, and Kubernetes manages "
            "Pods rather than managing containers directly."
        ),
        "contexts": [
            "Pods that run a single container. The one-container-per-Pod model is the "
            "most common Kubernetes use case; in this case, you can think of a Pod as a "
            "wrapper around a single container; Kubernetes manages Pods rather than managing "
            "the containers directly."
        ],
        "source": "pods.md",
    },
    {
        "question": "What are container probes in Kubernetes?",
        "answer": (
            "A probe is a diagnostic performed periodically by the kubelet on a container. "
            "The kubelet can use ExecAction, TCPSocketAction, or HTTPGetAction to perform the diagnostic."
        ),
        "contexts": [
            "A probe is a diagnostic performed periodically by the kubelet on a container. "
            "To perform a diagnostic, the kubelet can invoke different actions: "
            "ExecAction (performed with the help of the container runtime), "
            "TCPSocketAction (checked directly by the kubelet), "
            "HTTPGetAction (checked directly by the kubelet)."
        ],
        "source": "pods.md",
    },
    # ── configmaps.md ─────────────────────────────────────────────
    {
        "question": "What is a Kubernetes ConfigMap?",
        "answer": (
            "A ConfigMap is an API object used to store non-confidential data in key-value pairs. "
            "Pods can consume ConfigMaps as environment variables, command-line arguments, "
            "or as configuration files in a volume."
        ),
        "contexts": [
            "A ConfigMap is an API object used to store non-confidential data in key-value pairs. "
            "Pods can consume ConfigMaps as environment variables, command-line arguments, "
            "or as configuration files in a volume."
        ],
        "source": "configmaps.md",
    },
    {
        "question": "How do I use a ConfigMap to pass environment variables to a Pod?",
        "answer": (
            "Add envFrom with configMapRef to expose all keys as environment variables, "
            "or use env with configMapKeyRef to select individual keys."
        ),
        "contexts": [
            "For each container in your Pod specification, add an environment variable "
            "for each Configmap key that you want to use to the env[].valueFrom.configMapKeyRef field. "
            "The envFrom field instructs Kubernetes to create environment variables from the sources nested within it."
        ],
        "source": "configmaps.md",
    },
    {
        "question": "What is the maximum size of a Kubernetes ConfigMap?",
        "answer": (
            "A ConfigMap cannot exceed 1 MiB. "
            "For larger configuration data, use a volume or a separate database or file service."
        ),
        "contexts": [
            "A ConfigMap is not designed to hold large chunks of data. "
            "The data stored in a ConfigMap cannot exceed 1 MiB. "
            "If you need to store settings that are larger than this limit, "
            "you may want to consider mounting a volume or use a separate database or file service."
        ],
        "source": "configmaps.md",
    },
    {
        "question": "What is the difference between a ConfigMap and a Secret in Kubernetes?",
        "answer": (
            "ConfigMaps store non-sensitive configuration data. "
            "Secrets are for confidential data such as passwords and tokens."
        ),
        "contexts": [
            "ConfigMap does not provide secrecy or encryption. "
            "If the data you want to store are confidential, use a Secret rather than a ConfigMap, "
            "or use additional (third party) tools to keep your data private."
        ],
        "source": "configmaps.md",
    },
]
