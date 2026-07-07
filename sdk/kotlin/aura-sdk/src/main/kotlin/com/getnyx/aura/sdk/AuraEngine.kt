// PROJECT AURA — public SDK facade (Stage 9 §9).
//
// Idiomatic Kotlin wrapper over the handle-based NativeBindings. Exposes a
// Flow<DetectionEvent> whose semantics are equivalent to the core
// IWakeWordListener::onWakeWordDetected callback (invoked on the engine's Callback
// thread; safe to do work in the collector).
package com.getnyx.aura.sdk

import com.getnyx.aura.bindings.NativeBindings
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

/**
 * Wake-word engine handle.
 *
 * Usage:
 * ```
 * val engine = AuraEngine(context.filesDir.absolutePath)
 * engine.initialize(modelDir)
 * engine.addWakeWord("marvin")
 * lifecycleScope.launch { engine.detections().collect { toast("marvin!") } }
 * engine.start()
 * ```
 */
class AuraEngine(filesDir: String) : AutoCloseable {

    private val native = NativeBindings()
    private val handle: Long = native.nativeCreate(filesDir)

    /** Load models from [modelDir] and prepare the pipeline. */
    fun initialize(modelDir: String): Boolean = native.nativeInitialize(handle, modelDir)

    /** Register a wake word (v0 supports one). */
    fun addWakeWord(id: String, threshold: Float = 0.6f): Boolean =
        native.nativeAddWakeWord(handle, id, threshold)

    fun start(): Boolean = native.nativeStart(handle)

    fun stop(): Boolean = native.nativeStop(handle)

    /**
     * Cold [Flow] of detection events. Collecting installs the native listener;
     * v0 wires a single global listener, so a single active collector is assumed.
     */
    fun detections(): Flow<DetectionEvent> = callbackFlow {
        val callback = object : NativeBindings.Callback {
            override fun onDetection(
                correlationHi: Long,
                correlationLo: Long,
                confidence: Float,
                timestampNanos: Long,
                wakeWordIndex: Int,
            ) {
                trySend(
                    DetectionEvent(
                        CorrelationId(correlationHi, correlationLo),
                        confidence,
                        timestampNanos,
                        wakeWordIndex,
                    ),
                )
            }

            override fun onState(state: Int) { /* v0: state changes not surfaced on the flow */ }
            override fun onError(code: Int, message: String) { /* v0: errors not surfaced on the flow */ }
        }
        native.nativeSetListener(handle, callback)
        awaitClose { /* native listener lifetime is tied to the engine handle */ }
    }

    override fun close() {
        native.nativeStop(handle)
        native.nativeDestroy(handle)
    }
}
