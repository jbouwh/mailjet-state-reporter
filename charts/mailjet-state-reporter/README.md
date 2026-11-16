# mailjet-state-reporter Helm chart

Runs [mailjet-state-reporter](https://github.com/jbouwh/mailjet-state-reporter) as a Kubernetes CronJob.

The chart keeps configuration, state and logs strictly separated:

| Path / stream | Content                 | Source                                    | Access     |
| ------------- | ----------------------- | ----------------------------------------- | ---------- |
| `/config`     | `settings.yaml`         | ConfigMap (from the chart or existing)    | Read-only  |
| `/state`      | `sync_state.json`       | PersistentVolumeClaim                     | Read-write |
| stdout        | `DEBUG`/`INFO` lines    | n/a                                       | n/a        |
| stderr        | `WARNING`/`ERROR` lines | n/a                                       | n/a        |

The container runs as UID 2001 with a read-only root filesystem. Requires image `v0.3.10` or newer (the chart default).

## Install

The Mailjet master API credentials are read from a Secret with the keys `MAILJET_APP_ID` and `MAILJET_APP_SECRET`, for example synchronized from HashiCorp Vault:

```bash
kubectl -n mailjet-reporter create secret generic mailjet-credentials \
  --from-literal=MAILJET_APP_ID=xxxx --from-literal=MAILJET_APP_SECRET=xxxx
```

Install the chart with `settings.yaml` as a ConfigMap:

```bash
helm install mailjet-reporter ./charts/mailjet-state-reporter \
  --namespace mailjet-reporter --create-namespace \
  --set-file settings.content=config/settings.yaml \
  --set credentials.existingSecret=mailjet-credentials
```

After changing `settings.yaml`, run `helm upgrade` with the same `--set-file`; the next job uses the new ConfigMap.

To use a ConfigMap that is managed elsewhere (e.g. by Kustomize or ArgoCD), set `settings.existingConfigMap` instead of `settings.content`. The settings file must be stored under the key `settings.key` (default `settings.yaml`).

Start a manual run and show its logs:

```bash
kubectl -n mailjet-reporter create job --from=cronjob/mailjet-reporter-mailjet-state-reporter manual-run
kubectl -n mailjet-reporter logs job/manual-run
```

## Deploying from GitLab with ArgoCD

The chart is designed to be used from a GitLab deploy repository that is synced by ArgoCD. The chart itself stays in this (GitHub) repository and is pinned to a release tag; the GitLab repository only holds the values, `settings.yaml` and the Vault resources. A complete, tested example is in [`examples/gitlab-deploy`](examples/gitlab-deploy).

```
mailjet-reporter-deploy/             (GitLab)
├── .gitlab-ci.yml                   yamllint, helm lint/template, kustomize build, kubeconform
├── values.yaml                      Helm values for this chart
├── argocd/
│   └── application.yaml             ArgoCD Application (registered once, e.g. via app-of-apps)
└── k8s/
    ├── kustomization.yaml           namespace, Vault resources and the settings ConfigMap
    ├── settings.yaml                the reporter configuration
    ├── namespace.yaml
    ├── vault-auth.yaml              VaultAuth (Kubernetes auth)
    └── vault-static-secret.yaml     VaultStaticSecret -> Secret mailjet-credentials
```

How the parts fit together:

- **Chart**: the ArgoCD `Application` uses three sources: the chart from `https://github.com/jbouwh/mailjet-state-reporter.git` at path `charts/mailjet-state-reporter` and a release tag, the GitLab repository as `ref: deploy` for `$deploy/values.yaml`, and the GitLab path `k8s/` for the other resources. Use `releaseName: mailjet-state-reporter`, so the CronJob, ServiceAccount and PVC are named `mailjet-state-reporter` and `mailjet-state-reporter-state`.
- **`settings.yaml`**: Kustomize creates the ConfigMap `mailjet-reporter-settings` from `k8s/settings.yaml` with `disableNameSuffixHash: true`, and `values.yaml` points to it with `settings.existingConfigMap`. The name must be stable because the chart refers to it. Every job starts a new pod, so the next run always reads the current settings. Kustomize only loads files inside the kustomization directory, so `settings.yaml` lives in `k8s/`.
- **Credentials**: the Vault Secrets Operator creates the Secret `mailjet-credentials` (`credentials.existingSecret`). The `VaultAuth` uses the ServiceAccount `mailjet-state-reporter` that the chart creates.
- **State**: ArgoCD does not honour `helm.sh/resource-policy: keep`, so set `persistence.annotations` to `argocd.argoproj.io/sync-options: Prune=false,Delete=false`.
- **Versions**: keep the chart `targetRevision` in the `Application`, `REPORTER_REF` in `.gitlab-ci.yml` and `image.tag`/`image.digest` in `values.yaml` on the same release.
- **CI**: the pipeline clones the chart at `REPORTER_REF`, runs `helm lint --strict` and `helm template` with `values.yaml`, renders `k8s/` with Kustomize and validates everything with `kubeconform` (including the Vault CRDs). Make the pipeline required ("Pipelines must succeed" and a protected default branch), because ArgoCD syncs the default branch.
- **NOTES**: ArgoCD renders the chart with `helm template`, so the install notes are not shown. Start a manual run with `kubectl -n mailjet-reporter create job --from=cronjob/mailjet-state-reporter manual-run`.

The chart is available from the first release that contains `charts/mailjet-state-reporter`; the example uses `v0.3.11` as a placeholder for that release.

## Releasing

The chart is released together with the app: tagging a GitHub release also publishes the image. Before tagging, set `appVersion` in `Chart.yaml` to the new tag (e.g. `v0.3.11`) and increase the chart `version` when the chart changed, so the default image matches the chart at that tag.

## Values

| Key | Default | Description |
| --- | ------- | ----------- |
| `image.repository` | `jbouwh/mailjet-state-reporter` | Image repository |
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
