// PROJECT AURA — reference app entry point (Stage 7 §1). Requests mic permission,
// copies bundled placeholder models to the app files dir, starts the engine, and
// shows a toast + logcat line ("hey aura detected") on each detection event.
package com.getnyx.aura.app

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.widget.TextView
import android.widget.Toast
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.getnyx.aura.sdk.AuraEngine
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File

class MainActivity : Activity() {

    private companion object {
        const val TAG = "AURA"
        const val REQ_MIC = 1001
        val MODEL_ASSETS = listOf("aura.onnx", "aura_stage2.onnx", "silero_vad.onnx", "labels.json")
    }

    private var engine: AuraEngine? = null
    private lateinit var status: TextView
    private val scope = CoroutineScope(Dispatchers.Main)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        status = TextView(this).apply {
            text = "AURA — say \"hey aura\""
            gravity = Gravity.CENTER
            textSize = 22f
        }
        setContentView(status)

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startEngine()
        } else {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_MIC && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startEngine()
        } else {
            status.text = "Microphone permission denied"
        }
    }

    private fun startEngine() {
        val modelDir = File(filesDir, "models").apply { mkdirs() }
        copyModels(modelDir)

        val eng = AuraEngine(filesDir.absolutePath)
        engine = eng

        if (!eng.initialize(modelDir.absolutePath)) {
            status.text = "Engine init failed (are the placeholder models in assets/models/?)"
            Log.e(TAG, "initialize() failed — see 'no modelDir'/model-load logs")
            return
        }
        eng.addWakeWord("hey aura")

        // Collect detections on the main scope; the SDK Flow is fed from the
        // engine's Callback thread (Stage 7 §4), so UI work here is safe.
        scope.launch {
            eng.detections().collect { ev ->
                val msg = "hey aura detected (conf=%.2f)".format(ev.confidence)
                Log.i(TAG, "$msg cid=${ev.correlationId} ts=${ev.timestampNanos}")
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
                status.text = msg
            }
        }

        if (eng.start()) {
            status.text = "Listening — say \"hey aura\""
            Log.i(TAG, "engine started")
        } else {
            status.text = "Engine start failed"
        }
    }

    private fun copyModels(dir: File) {
        for (name in MODEL_ASSETS) {
            val out = File(dir, name)
            if (out.exists() && out.length() > 0) continue
            try {
                assets.open("models/$name").use { input ->
                    out.outputStream().use { input.copyTo(it) }
                }
            } catch (e: Exception) {
                Log.w(TAG, "placeholder model asset missing: models/$name (${e.message})")
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        engine?.close()
        engine = null
    }
}
