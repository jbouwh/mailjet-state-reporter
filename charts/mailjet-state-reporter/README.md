# mailjet-state-reporter Helm chart

Runs [mailjet-state-reporter](https://github.com/jbouwh/mailjet-state-reporter) as a Kubernetes CronJob.

The chart keeps configuration, state and logs strictly separated:

| Path / stream | Content                 | Source                                    | Access     |
| ------------- | ----------------------- | ----------------------------------------- | ---------- |
| `/config`     | `settings.yaml`         | ConfigMap (from the chart or existing)    | Read-only  |
| `/state`      | `sync_state.json`       | PersistentVolumeClaim                     | Read-write |
| stdout        | `DEBUG`/`INFO` lines    | n/a                                       | n/a        |
| stderr        | `WARNING`/`ERROR` lines | n/a                                       | n/a        |

The container runs as UID 2001 with a read-only root filesystem. Requires image `v0.3.10` or newer; by default the chart uses its `appVersion` (`v0.3.11`).

## Install

The Mailjet master API credentials are read from a Secret with the keys `MAILJET_APP_ID` and `MAILJET_APP_SECRET`. HashiCorp Vault is optional: the Secret can be synchronized from Vault, or created in another way, for example:

```bash
kubectl -n mailjet-reporter create secret generic mailjet-credentials \
  --from-literal=MAILJET_APP_ID=xxxx --from-literal=MAILJET_APP_SECRET=xxxx
```

The chart is published as an OCI artifact on the GitHub Container Registry: `oci://ghcr.io/jbouwh/charts/mailjet-state-reporter`. The chart version is the release without the leading `v` (chart `0.3.11` = image `v0.3.11`). Install it with `settings.yaml` as a ConfigMap:

```bash
helm install mailjet-reporter oci://ghcr.io/jbouwh/charts/mailjet-state-reporter --version 0.3.11 \
  --namespace mailjet-reporter --create-namespace \
  --set-file settings.content=config/settings.yaml \
  --set credentials.existingSecret=mailjet-credentials
```

From a checkout of this repository, use `./charts/mailjet-state-reporter` instead of the `oci://` reference (without `--version`).

### Using a registry proxy (Harbor)

When charts and images are pulled through a proxy cache such as Harbor, put the proxy prefix in front of the registry paths. For example, with the Harbor proxy cache projects `ghcr` (for ghcr.io) and `dockerhub` (for Docker Hub):

```bash
helm install mailjet-reporter oci://harbor.example.com/ghcr/jbouwh/charts/mailjet-state-reporter --version 0.3.11 \
  --namespace mailjet-reporter --create-namespace \
  --set image.repository=harbor.example.com/dockerhub/jbouwh/mailjet-state-reporter \
  --set-file settings.content=config/settings.yaml \
  --set credentials.existingSecret=mailjet-credentials
```

Run `helm registry login harbor.example.com` first when the Harbor project is not public, and add `imagePullSecrets` when the cluster needs credentials to pull the image. A pinned `image.digest` also works through the proxy.

After changing `settings.yaml`, run `helm upgrade` with the same `--set-file`; the next job uses the new ConfigMap.

To use a ConfigMap that is managed elsewhere (e.g. by Kustomize or ArgoCD), set `settings.existingConfigMap` instead of `settings.content`. The settings file must be stored under the key `settings.key` (default `settings.yaml`).

Start a manual run and show its logs:

```bash
kubectl -n mailjet-reporter create job --from=cronjob/mailjet-reporter-mailjet-state-reporter manual-run
kubectl -n mailjet-reporter logs job/manual-run
```

## Testing on Docker Desktop

[`examples/docker-desktop`](examples/docker-desktop) contains a test setup for the single-node Kubernetes cluster of Docker Desktop: `values.yaml` (suspended CronJob, small PVC on the default StorageClass (`standard` in kind mode, `hostpath` in kubeadm mode), state removed on uninstall), a test `settings.yaml` and `test.sh`. Enable Kubernetes in Docker Desktop (*Settings > Kubernetes*) and make sure `kubectl` and `helm` are installed. In WSL, use the Windows kubeconfig if `~/.kube/config` does not exist, e.g. `export KUBECONFIG=/mnt/c/Users/<user>/.kube/config`. Docker Desktop must be able to write that file: if Kubernetes fails to start with `failed to write KUBECONFIG ... Access is denied`, remove the read-only attribute (`attrib -R %USERPROFILE%\.kube\config`) and restart Kubernetes. Check the state with `docker desktop kubernetes status`.

```bash
cd charts/mailjet-state-reporter/examples/docker-desktop
./test.sh                     # install the chart from this checkout and run a job
CHART=oci://ghcr.io/jbouwh/charts/mailjet-state-reporter CHART_VERSION=0.3.11 ./test.sh   # published chart
./test.sh cleanup             # remove the release and the namespace
```

`test.sh` installs the release `mailjet-state-reporter` in the namespace `mailjet-reporter-test`, creates the Secret `mailjet-credentials` from `MAILJET_APP_ID` and `MAILJET_APP_SECRET`, starts a job from the CronJob and follows its logs. Without these variables it uses dummy credentials: the run then fails at the Mailjet API with an error on stderr, which still tests the ConfigMap, the read-only `/config`, the `/state` volume and the logging. With real credentials, set a real subaccount and your own address as recipient in `settings.yaml` (or point `SETTINGS` to another file): the run then sends a real report.

## Deploying from GitLab with ArgoCD

The chart is designed to be used from a GitLab deploy repository that is synced by ArgoCD. GitHub only hosts the source code and publishes the chart (ghcr.io) and the image (Docker Hub); ArgoCD and the GitLab pipeline pull both through the Harbor proxy cache, so they do not access GitHub or Docker Hub directly. The GitLab deploy repository only holds the values, `settings.yaml` and, optionally, the Vault resources. A complete, tested example is in [`examples/gitlab-deploy`](examples/gitlab-deploy).

```
mailjet-reporter-deploy/             (GitLab)
├── .gitlab-ci.yml                   yamllint, helm pull/lint/template, kustomize build, kubeconform
├── .yamllint.yaml                   yamllint configuration
├── values.yaml                      Helm values for this chart
├── argocd/
│   ├── application.yaml             ArgoCD Application (registered once, e.g. via app-of-apps)
│   └── chart-repository.yaml        ArgoCD repository Secret for the OCI chart in Harbor
└── k8s/
    ├── kustomization.yaml           namespace, the settings ConfigMap and the optional vault component
    ├── settings.yaml                the reporter configuration
    ├── namespace.yaml
    └── vault/                       optional Kustomize component
        ├── kustomization.yaml
        ├── vault-auth.yaml          VaultAuth (Kubernetes auth)
        └── vault-static-secret.yaml VaultStaticSecret -> Secret mailjet-credentials
```

How the parts fit together:

- **Harbor**: the example assumes the Harbor proxy cache projects `harbor.example.com/ghcr` (for ghcr.io), `harbor.example.com/dockerhub` (for Docker Hub) and `harbor.example.com/k8s` (for registry.k8s.io). Replace the prefixes with your own. Official Docker Hub images are under `library/` in a proxy cache project (e.g. `harbor.example.com/dockerhub/library/python`).
- **Chart**: the ArgoCD `Application` uses three sources: the OCI chart `mailjet-state-reporter` from `harbor.example.com/ghcr/jbouwh/charts` at a chart version (`targetRevision: 0.3.11`), the GitLab repository as `ref: deploy` for `$deploy/values.yaml`, and the GitLab path `k8s/` for the other resources. For an OCI Helm source, ArgoCD needs a repository Secret with `type: helm` and `enableOCI: "true"` for that URL (`argocd/chart-repository.yaml`; the `repoURL` has no `oci://` prefix). Use `releaseName: mailjet-state-reporter`, so the CronJob, ServiceAccount and PVC are named `mailjet-state-reporter` and `mailjet-state-reporter-state`.
- **Image**: `values.yaml` sets `image.repository` to the Harbor prefix of the Docker Hub image (`harbor.example.com/dockerhub/jbouwh/mailjet-state-reporter`) and pins `image.tag` and `image.digest`.
- **`settings.yaml`**: Kustomize creates the ConfigMap `mailjet-reporter-settings` from `k8s/settings.yaml` with `disableNameSuffixHash: true`, and `values.yaml` points to it with `settings.existingConfigMap`. The name must be stable because the chart refers to it. Every job starts a new pod, so the next run always reads the current settings. Kustomize only loads files inside the kustomization directory, so `settings.yaml` lives in `k8s/`.
- **Credentials**: the chart reads the Secret `mailjet-credentials` (`credentials.existingSecret`). In the example the optional `vault` component lets the Vault Secrets Operator create it; its `VaultAuth` uses the ServiceAccount `mailjet-state-reporter` that the chart creates. Without Vault, see [Credentials without Vault](#credentials-without-vault).
- **State**: ArgoCD does not honour `helm.sh/resource-policy: keep`, so set `persistence.annotations` to `argocd.argoproj.io/sync-options: Prune=false,Delete=false`.
- **Versions**: keep the chart `targetRevision` in the `Application`, `CHART_VERSION` in `.gitlab-ci.yml` and `image.tag`/`image.digest` in `values.yaml` on the same release (chart `0.3.11` = image `v0.3.11`).
- **CI**: all job images are pulled through the Harbor prefixes (`DOCKERHUB_PROXY`, `GHCR_PROXY`, `K8S_REGISTRY_PROXY`). The pipeline pulls the chart (`CHART`, `CHART_VERSION`), runs `helm lint --strict` and `helm template` with `values.yaml`, renders `k8s/` with Kustomize and validates everything with `kubeconform` (including CRDs such as the Vault resources). When the Harbor projects are not public, set the masked CI/CD variables `HARBOR_USERNAME` and `HARBOR_PASSWORD` (e.g. a robot account) for the chart, and `DOCKER_AUTH_CONFIG` for the job images. Make the pipeline required ("Pipelines must succeed" and a protected default branch), because ArgoCD syncs the default branch.
- **Other downloads**: `pip` (yamllint) uses PyPI and kubeconform downloads its schemas (Kubernetes schemas and the CRD catalog) from GitHub. If the runners cannot reach them, use internal mirrors and adjust the pip index and `-schema-location` options.
- **NOTES**: ArgoCD renders the chart with `helm template`, so the install notes are not shown. Start a manual run with `kubectl -n mailjet-reporter create job --from=cronjob/mailjet-state-reporter manual-run`.

The OCI chart is available from release `v0.3.11` (chart `0.3.11`), which is also the version used in the example.

### Alternative: a GitLab mirror of this repository

Without a registry proxy, the chart can also be used from a Git repository. Create a GitLab project with a **pull mirror** of `https://github.com/jbouwh/mailjet-state-reporter.git` (branches and release tags are mirrored), and use it as the chart source in the `Application`:

```yaml
- repoURL: https://gitlab.example.com/example-group/mailjet-state-reporter.git
  targetRevision: v0.3.11
  path: charts/mailjet-state-reporter
```

In `.gitlab-ci.yml`, replace `helm pull` with a clone of the mirror at the release tag (`git clone --depth 1 --branch v0.3.11 "https://gitlab-ci-token:${CI_JOB_TOKEN}@${CI_SERVER_HOST}/<mirror path>.git"`), and add the deploy project to the job token allowlist of the mirror (*Settings > CI/CD > Job token permissions*). Check that a new release tag has been mirrored before you use it.

## Credentials without Vault

The chart does not depend on Vault: it only needs a Secret with the keys `MAILJET_APP_ID` and `MAILJET_APP_SECRET`, set with `credentials.existingSecret`. To use the GitLab example without Vault, remove the `vault` component from `k8s/kustomization.yaml` (and the `k8s/vault/` folder), keep `credentials.existingSecret: mailjet-credentials` in `values.yaml`, and create the Secret in one of these ways:

- **Manually**, once per cluster. The Secret is not in Git, so ArgoCD does not manage or prune it:

  ```bash
  kubectl -n mailjet-reporter create secret generic mailjet-credentials \
    --from-literal=MAILJET_APP_ID=xxxx --from-literal=MAILJET_APP_SECRET=xxxx
  ```

  To rotate the credentials, run the same command with `--dry-run=client -o yaml | kubectl apply -f -`. The Secret is removed when the namespace is deleted.
- **Sealed Secrets** (requires the Sealed Secrets controller): commit an encrypted `SealedSecret` to `k8s/` and add it to `resources` in `k8s/kustomization.yaml`:

  ```bash
  kubectl -n mailjet-reporter create secret generic mailjet-credentials --dry-run=client -o yaml \
    --from-literal=MAILJET_APP_ID=xxxx --from-literal=MAILJET_APP_SECRET=xxxx \
    | kubeseal -o yaml > k8s/mailjet-credentials-sealed.yaml
  ```
- **External Secrets Operator** or another secret manager: create an `ExternalSecret` (or equivalent) with target `mailjet-credentials` instead of the `vault` component.

Do not use `credentials.create` with real credentials in a values file in Git; it is meant for local tests only.

## Releasing

The chart is released together with the app. Publishing a GitHub release runs two workflows: one pushes the image to Docker Hub, the other packages the chart and pushes it to `oci://ghcr.io/jbouwh/charts/mailjet-state-reporter`. The published chart gets version `X.Y.Z` and appVersion `vX.Y.Z` from the release tag `vX.Y.Z`, so the default image always matches the chart. Also set `version` and `appVersion` in `Chart.yaml` to the new release before tagging, so the chart in Git (e.g. a GitLab mirror) matches the published chart.

To publish the chart of an existing release (e.g. `v0.3.11`), run the *Publish Helm chart to GHCR* workflow manually with that tag. After the first push, make the `charts/mailjet-state-reporter` package public in the GitHub package settings, so it can be pulled without credentials (also by Harbor).

## Values

| Key | Default | Description |
| --- | ------- | ----------- |
| `image.repository` | `jbouwh/mailjet-state-reporter` | Image repository; include a registry or proxy prefix if needed, e.g. `harbor.example.com/dockerhub/jbouwh/mailjet-state-reporter` |
| `image.tag` | chart `appVersion` | Image tag |
| `image.digest` | `""` | Optional digest (`sha256:...`) to pin the image |
| `schedule` | `"0 6 * * *"` | Cron schedule; `report_days` in `settings.yaml` decides if a report is sent |
| `timeZone` | `Europe/Amsterdam` | Time zone of the schedule |
| `suspend` | `false` | Suspend the CronJob |
| `concurrencyPolicy` | `Forbid` | Never run two jobs at the same time |
| `backoffLimit` | `0` | No retries, to avoid sending reports twice |
| `activeDeadlineSeconds` | `1800` | Maximum run time of a job |
| `ttlSecondsAfterFinished` | `null` | Optionally remove finished jobs |
| `settings.content` | `""` | Content of `settings.yaml`; use `--set-file settings.content=<file>` |
| `settings.existingConfigMap` | `""` | Use an existing ConfigMap instead |
| `settings.key` | `settings.yaml` | Key of the settings file in the ConfigMap |
| `credentials.existingSecret` | `""` | Existing Secret with the Mailjet credentials |
| `credentials.appIdKey` / `credentials.appSecretKey` | `MAILJET_APP_ID` / `MAILJET_APP_SECRET` | Keys in the Secret |
| `credentials.create` | `false` | Let the chart create the Secret from `credentials.appId` and `credentials.appSecret` |
| `persistence.existingClaim` | `""` | Use an existing PVC for `/state` |
| `persistence.size` | `100Mi` | Size of the PVC |
| `persistence.storageClass` | `""` | StorageClass of the PVC |
| `persistence.keep` | `true` | Keep the PVC on `helm uninstall` (`helm.sh/resource-policy: keep`) |
| `persistence.annotations` | `{}` | Extra PVC annotations, e.g. `argocd.argoproj.io/sync-options: Prune=false,Delete=false` |
| `logFile` | `""` | Optional log file; an `emptyDir` is mounted on its directory. Must not be in `/config` or `/state` |
| `logVolume.sizeLimit` | `50Mi` | Size limit of the log `emptyDir` |
| `extraEnv` | `[]` | Extra environment variables |
| `serviceAccount.create` | `true` | Create a ServiceAccount (no API token mounted) |
| `podSecurityContext` / `securityContext` | UID 2001, read-only root filesystem, no capabilities | Security settings |
| `resources` | 50m / 64Mi request, 256Mi limit | Container resources |
| `nodeSelector`, `tolerations`, `affinity`, `podAnnotations`, `podLabels`, `imagePullSecrets` | empty | Scheduling and metadata |

The files in `ci/` are example values used to lint and test the chart. The files in `examples/` are not part of the chart package.
