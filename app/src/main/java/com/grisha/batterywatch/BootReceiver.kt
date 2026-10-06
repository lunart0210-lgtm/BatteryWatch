package com.grisha.batterywatch

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action in BOOT_ACTIONS) {
            ContextCompat.startForegroundService(
                context, Intent(context, BatteryWatchService::class.java)
            )
        }
    }

    companion object {
        private val BOOT_ACTIONS = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            "android.intent.action.QUICKBOOT_POWERON",      // MIUI / часть прошивок
            "com.htc.intent.action.QUICKBOOT_POWERON"
        )
    }
}
