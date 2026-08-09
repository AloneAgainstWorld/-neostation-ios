package com.neogamelab.neostation

import android.database.Cursor
import android.database.MatrixCursor
import android.os.CancellationSignal
import android.os.ParcelFileDescriptor
import android.provider.DocumentsContract.Document
import android.provider.DocumentsContract.Root
import android.provider.DocumentsProvider
import android.webkit.MimeTypeMap

import java.io.File
import java.io.FileNotFoundException

class NeoDocumentsProvider : DocumentsProvider() {

    companion object {
        // Constants
        private const val DEFAULT_ROOT_ID = "root"
        private const val ROOT_NAME = "NeoStation"

        // Columns
        private val DEFAULT_ROOT_PROJECTION: Array<String> = arrayOf(
            Root.COLUMN_ROOT_ID,
            Root.COLUMN_MIME_TYPES,
            Root.COLUMN_FLAGS,
            Root.COLUMN_ICON,
            Root.COLUMN_TITLE,
            Root.COLUMN_SUMMARY,
            Root.COLUMN_DOCUMENT_ID,
            Root.COLUMN_AVAILABLE_BYTES
        )

        private val DEFAULT_DOCUMENT_PROJECTION: Array<String> = arrayOf(
            Document.COLUMN_DOCUMENT_ID,
            Document.COLUMN_MIME_TYPE,
            Document.COLUMN_DISPLAY_NAME,
            Document.COLUMN_LAST_MODIFIED,
            Document.COLUMN_FLAGS,
            Document.COLUMN_SIZE
        )
    }

    private lateinit var baseDir: File

    override fun onCreate(): Boolean {
        val context = context ?: return false

        // Respect user-configured custom path stored by Flutter's SharedPreferences.
        val prefs = context.getSharedPreferences(
            "FlutterSharedPreferences",
            android.content.Context.MODE_PRIVATE,
        )
        val customPath = prefs.getString("flutter.custom_user_data_path", null)

        baseDir = if (!customPath.isNullOrEmpty()) {
            File(customPath)
        } else {
            val root = context.getExternalFilesDir(null) ?: return false
            File(root, "user-data")
        }

        if (!baseDir.exists()) {
            baseDir.mkdirs()
        }
        return true
    }

    override fun queryRoots(projection: Array<out String>?): Cursor {
        val result = MatrixCursor(projection ?: DEFAULT_ROOT_PROJECTION)
        val row = result.newRow()

        row.add(Root.COLUMN_ROOT_ID, DEFAULT_ROOT_ID)
        row.add(Root.COLUMN_ICON, R.mipmap.launcher_icon)
        row.add(Root.COLUMN_TITLE, ROOT_NAME)
        // row.add(Root.COLUMN_SUMMARY, "App Data") // Removed to avoid confusion
        row.add(Root.COLUMN_DOCUMENT_ID, getDocIdForFile(baseDir))
        row.add(Root.COLUMN_MIME_TYPES, "*/*")
        
        // Flags: supports create, is child (can be browsed)
        row.add(Root.COLUMN_FLAGS, Root.FLAG_SUPPORTS_CREATE or Root.FLAG_SUPPORTS_IS_CHILD)
        row.add(Root.COLUMN_AVAILABLE_BYTES, baseDir.freeSpace)

        return result
    }

    override fun queryChildDocuments(
        parentDocumentId: String?,
        projection: Array<out String>?,
        sortOrder: String?
    ): Cursor {
        val result = MatrixCursor(projection ?: DEFAULT_DOCUMENT_PROJECTION)
        val parent = getFileForDocId(parentDocumentId)
        
        parent.listFiles()?.forEach { file ->
            includeFile(result, file)
        }
        
        return result
    }

    override fun queryDocument(documentId: String?, projection: Array<out String>?): Cursor {
        val result = MatrixCursor(projection ?: DEFAULT_DOCUMENT_PROJECTION)
        val file = getFileForDocId(documentId)
        
        if (!file.exists()) {
            throw FileNotFoundException("Missing file for id: $documentId at ${file.absolutePath}")
        }
        
        includeFile(result, file)
        return result
    }

    override fun openDocument(
        documentId: String?,
        mode: String?,
        signal: CancellationSignal?
    ): ParcelFileDescriptor {
        val file = getFileForDocId(documentId)
        val accessMode = ParcelFileDescriptor.parseMode(mode)
        return ParcelFileDescriptor.open(file, accessMode)
    }

    override fun getDocumentType(documentId: String?): String {
        return getMimeType(getFileForDocId(documentId))
    }

    // --- Helpers ---

    private fun getDocIdForFile(file: File): String {
        var path = file.absolutePath
        val rootPath = baseDir.absolutePath
        
        if (path == rootPath) return DEFAULT_ROOT_ID
        
        if (path.startsWith(rootPath)) {
            path = path.substring(rootPath.length)
            if (path.startsWith("/")) path = path.substring(1)
            return if (path.isEmpty()) DEFAULT_ROOT_ID else path
        }
        
        return DEFAULT_ROOT_ID
    }

    private fun getFileForDocId(docId: String?): File {
        if (docId == DEFAULT_ROOT_ID || docId.isNullOrEmpty()) {
            return baseDir
        }
        return File(baseDir, docId)
    }

    private fun includeFile(result: MatrixCursor, file: File) {
        val row = result.newRow()
        row.add(Document.COLUMN_DOCUMENT_ID, getDocIdForFile(file))
        row.add(Document.COLUMN_DISPLAY_NAME, file.name)
        
        val mimeType = getMimeType(file)
        row.add(Document.COLUMN_MIME_TYPE, mimeType)
        
        var flags = 0
        if (file.isDirectory) {
            flags = flags or Document.FLAG_DIR_SUPPORTS_CREATE
        } else {
            flags = flags or Document.FLAG_SUPPORTS_WRITE
            flags = flags or Document.FLAG_SUPPORTS_DELETE
        }
        row.add(Document.COLUMN_FLAGS, flags)
        
        row.add(Document.COLUMN_SIZE, file.length())
        row.add(Document.COLUMN_LAST_MODIFIED, file.lastModified())
    }

    private fun getMimeType(file: File): String {
        if (file.isDirectory) return Document.MIME_TYPE_DIR
        
        // Manual extension extraction from filename (avoiding getFileExtensionFromUrl which fails with spaces)
        val name = file.name
        val lastDot = name.lastIndexOf('.')
        if (lastDot >= 0) {
            val extension = name.substring(lastDot + 1).lowercase()
            return MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension) ?: "application/octet-stream"
        }
        return "application/octet-stream"
    }
}
