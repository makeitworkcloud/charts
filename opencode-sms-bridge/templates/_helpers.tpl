{{- define "opencode-sms-bridge.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "opencode-sms-bridge.fullname" -}}
{{- default (include "opencode-sms-bridge.name" .) .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "opencode-sms-bridge.labels" -}}
app: {{ include "opencode-sms-bridge.fullname" . }}
app.kubernetes.io/name: {{ include "opencode-sms-bridge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
