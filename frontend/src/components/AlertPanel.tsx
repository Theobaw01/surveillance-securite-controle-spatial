"use client";

import { AlertTriangle, Bell, CheckCircle } from "lucide-react";
import clsx from "clsx";

interface AlertItem {
  id: number;
  alert_type: string;
  message: string;
  datetime: string;
  acknowledged: boolean;
}

interface Props {
  alerts: AlertItem[];
}

function getAlertIcon(type: string) {
  if (type.includes("critical") || type.includes("danger"))
    return <AlertTriangle className="w-4 h-4 text-red-400" />;
  if (type.includes("warning"))
    return <Bell className="w-4 h-4 text-yellow-400" />;
  return <CheckCircle className="w-4 h-4 text-blue-400" />;
}

export default function AlertPanel({ alerts }: Props) {
  if (alerts.length === 0) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
          <Bell className="w-4 h-4" />
          Alertes
        </h3>
        <p className="text-sm text-gray-500">Aucune alerte active</p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
        <Bell className="w-4 h-4" />
        Alertes
        <span className="ml-auto text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full">
          {alerts.filter((a) => !a.acknowledged).length} non lue(s)
        </span>
      </h3>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={clsx(
              "flex items-start gap-3 p-3 rounded-lg border transition-colors",
              alert.acknowledged
                ? "border-surface-border bg-surface/50 opacity-60"
                : "border-yellow-500/30 bg-yellow-500/5"
            )}
          >
            {getAlertIcon(alert.alert_type)}
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200 line-clamp-2">
                {alert.message}
              </p>
              <p className="text-[11px] text-gray-500 mt-1">
                {alert.datetime}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
