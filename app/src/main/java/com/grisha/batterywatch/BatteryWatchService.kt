package com.grisha.batterywatch

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class BatteryWatchService : Service() {

    companion object {
        const val LOW = 20
        const val HIGH = 80
        private const val HYSTERESIS = 5
        private const val CH_ONGOING = "battery_ongoing"
        private const val CH_ALERT = "battery_alert"
        private const val ID_ONGOING = 1
        private const val ID_ALERT = 2
    }

    private var lowNotified = false
    private var highNotified = false

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
            val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
            if (level < 0 || scale <= 0) return
            val pct = level * 100 / scale

            val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            val charging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL

            updateOngoing(pct, charging)

            if (charging && pct >= HIGH && !highNotified) {
                alert("Заряд $pct% — отключите зарядку")
                highNotified = true
            }
            // Гистерезис: повторное уведомление только после ухода на 5% от порога
            if (pct <= HIGH - HYSTERESIS) highNotified = false

            if (!charging && pct <= LOW && !lowNotified) {
                alert("Заряд $pct% — пора на зарядку")
                lowNotified = true
            }
            if (pct >= LOW + HYSTERESIS) lowNotified = false
        }
    }

    override fun onCreate() {
        super.onCreate()
        createChannels()
        val notification = buildOngoing("Слежу за зарядом…")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(ID_ONGOING, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(ID_ONGOING, notification)
        }
        registerReceiver(receiver, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        unregisterReceiver(receiver)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannels() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CH_ONGOING, "Фоновое отслеживание", NotificationManager.IMPORTANCE_MIN)
        )
        nm.createNotificationChannel(
            NotificationChannel(CH_ALERT, "Пороги заряда", NotificationManager.IMPORTANCE_HIGH).apply {
                enableVibration(true)
            }
        )
    }

    private fun openAppIntent(): PendingIntent = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )

    private fun buildOngoing(text: String) = NotificationCompat.Builder(this, CH_ONGOING)
        .setSmallIcon(android.R.drawable.ic_lock_idle_charging)
        .setContentTitle("Battery Watch")
        .setContentText(text)
        .setOngoing(true)
        .setContentIntent(openAppIntent())
        .build()

    private fun updateOngoing(pct: Int, charging: Boolean) {
        val state = if (charging) "заряжается" else "разряжается"
        getSystemService(NotificationManager::class.java)
            .notify(ID_ONGOING, buildOngoing("$pct% — $state (пороги $LOW–$HIGH%)"))
    }

    private fun alert(text: String) {
        val n = NotificationCompat.Builder(this, CH_ALERT)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Battery Watch")
            .setContentText(text)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(openAppIntent())
            .build()
        getSystemService(NotificationManager::class.java).notify(ID_ALERT, n)
    }
}
