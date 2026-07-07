// PROJECT AURA — the JNI binding surface (Stage 9 §9).
//
// This is the generated-layer stand-in: a thin, handle-based (jlong -> C++ engine
// pointer) declaration set, deliberately mechanical so a future codegen tool
// (ADR-Binding) can replace it without any change to :aura-sdk above. It exposes
// NO idiomatic API — that lives in the aura-sdk wrapper.
package com.getnyx.aura.bindings

class NativeBindings {

    /** Native -> JVM detection/state/error callbacks. Invoked on the engine's
     *  Callback thread (Stage 7 §4), marshalled by the JNI listener adapter. */
    interface Callback {
        fun onDetection(
            correlationHi: Long,
            correlationLo: Long,
            confidence: Float,
            timestampNanos: Long,
            wakeWordIndex: Int,
        )
        fun onState(state: Int)
        fun onError(code: Int, message: String)
    }

    external fun nativeCreate(filesDir: String): Long
    external fun nativeInitialize(handle: Long, modelDir: String): Boolean
    external fun nativeAddWakeWord(handle: Long, id: String, threshold: Float): Boolean
    external fun nativeSetListener(handle: Long, callback: Callback)
    external fun nativeStart(handle: Long): Boolean
    external fun nativeStop(handle: Long): Boolean
    external fun nativeDestroy(handle: Long)

    companion object {
        init {
            System.loadLibrary("aura_jni")
        }
    }
}
