{{- define "opencode-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "opencode-server.fullname" -}}
{{- default (include "opencode-server.name" .) .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}
