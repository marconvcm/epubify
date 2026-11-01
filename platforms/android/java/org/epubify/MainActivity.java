package org.epubify;

import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.ColorDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.view.WindowInsetsController;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import org.kivy.android.PythonActivity;
import org.qtproject.qt.android.EpubifyBridge;

/**
 * Bridges Android-only features to Python without JNI on the Python side.
 *
 * Python writes "system-bars.txt" ("#RRGGBB light|dark") to apply system bar colors, and reads
 * "open-intent.txt" to learn which document another app asked Epubify to open.
 */
public class MainActivity extends PythonActivity {
    private static final String TAG = "EpubifyActivity";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private long barsStamp = 0;
    private final Runnable poll =
            new Runnable() {
                @Override
                public void run() {
                    applyBars();
                    handler.postDelayed(this, 400);
                }
            };

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleIntent(getIntent());
        handler.post(poll);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        setIntent(intent);
        handleIntent(intent);
        super.onNewIntent(intent);
        EpubifyBridge.newIntent(intent);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        // PythonActivity never forwards to Qt, which would leave file dialogs without a result.
        EpubifyBridge.activityResult(requestCode, resultCode, data);
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(poll);
        super.onDestroy();
    }

    private void handleIntent(Intent intent) {
        if (intent == null) return;
        String action = intent.getAction();
        Uri uri = null;
        if (Intent.ACTION_VIEW.equals(action)) {
            uri = intent.getData();
        } else if (Intent.ACTION_SEND.equals(action)) {
            uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        }
        if (uri == null) return;
        // The grant only lives as long as this intent, so keep it readable for the process.
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            File target = new File(getFilesDir(), "open-intent.txt");
            File partial = new File(getFilesDir(), "open-intent.tmp");
            try (FileOutputStream out = new FileOutputStream(partial)) {
                out.write(uri.toString().getBytes(StandardCharsets.UTF_8));
            }
            partial.renameTo(target);
        } catch (Exception e) {
            Log.e(TAG, "Unable to hand the document to Python", e);
        }
        intent.setAction(Intent.ACTION_MAIN);
        intent.setData(null);
    }

    private void applyBars() {
        File file = new File(getFilesDir(), "system-bars.txt");
        long stamp = file.lastModified();
        if (stamp == 0 || stamp == barsStamp) return;
        try {
            String[] parts = new String(java.nio.file.Files.readAllBytes(file.toPath()),
                    StandardCharsets.UTF_8).trim().split("\\s+");
            int color = Color.parseColor(parts[0]);
            boolean light = parts.length > 1 && parts[1].equals("light");
            Window window = getWindow();
            window.addFlags(android.view.WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
            window.setBackgroundDrawable(new ColorDrawable(color));
            window.setStatusBarColor(color);
            window.setNavigationBarColor(color);
            if (Build.VERSION.SDK_INT >= 29) {
                window.setNavigationBarContrastEnforced(false);
                window.setStatusBarContrastEnforced(false);
            }
            if (Build.VERSION.SDK_INT >= 30) {
                WindowInsetsController controller = window.getInsetsController();
                if (controller != null) {
                    int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                            | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                    controller.setSystemBarsAppearance(light ? mask : 0, mask);
                }
            } else {
                View decor = window.getDecorView();
                int flags = decor.getSystemUiVisibility();
                int mask = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
                if (Build.VERSION.SDK_INT >= 26) mask |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                decor.setSystemUiVisibility(light ? flags | mask : flags & ~mask);
            }
            barsStamp = stamp;
        } catch (Exception e) {
            Log.e(TAG, "Unable to color the system bars", e);
            barsStamp = stamp;
        }
    }
}
