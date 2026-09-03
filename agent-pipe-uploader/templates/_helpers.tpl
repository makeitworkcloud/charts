{{- define "agent-pipe-uploader.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agent-pipe-uploader.fullname" -}}
{{- default (include "agent-pipe-uploader.name" .) .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agent-pipe-uploader.labels" -}}
app: {{ include "agent-pipe-uploader.fullname" . }}
app.kubernetes.io/name: {{ include "agent-pipe-uploader.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
