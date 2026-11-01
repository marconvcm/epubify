package org.qtproject.qt.android;

import android.content.Intent;

/**
 * The p4a PythonActivity swallows onActivityResult/onNewIntent without calling QtActivity, so Qt
 * never sees file dialog results. QtNative's entry point is package-private; expose it here.
 */
public final class EpubifyBridge {
    private EpubifyBridge() {}

    public static void activityResult(int requestCode, int resultCode, Intent data) {
        QtNative.onActivityResult(requestCode, resultCode, data);
    }

    public static void newIntent(Intent intent) {
        QtNative.onNewIntent(intent);
    }
}
