"""
Google Drive Client for Storsafe Dashboard.

Provides file discovery and download from Google Drive for remote file processing.
Uses the same service account as Google Sheets.
"""

import io
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from ..config import Config

logger = logging.getLogger(__name__)


# Google Drive API scopes
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]


class GoogleDriveClient:
    """Client for interacting with Google Drive."""
    
    def __init__(self):
        self._service = None
        self._credentials = None
    
    def _get_credentials(self):
        """Get Google service account credentials."""
        if self._credentials:
            return self._credentials
        
        creds_dict = Config.get_google_credentials()
        if not creds_dict:
            raise ValueError(
                "Google credentials not configured. "
                "Set SERVICE_ACCOUNT_JSON environment variable."
            )
        
        self._credentials = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=SCOPES
        )
        return self._credentials
    
    def _get_service(self):
        """Get Google Drive API service."""
        if self._service:
            return self._service
        
        creds = self._get_credentials()
        self._service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return self._service
    
    def list_folders(
        self, 
        parent_id: str = None,
        name_contains: str = None,
    ) -> List[Dict[str, Any]]:
        """
        List folders in Google Drive.
        
        Args:
            parent_id: Parent folder ID (optional)
            name_contains: Filter folders by name substring
            
        Returns:
            List of folder dicts with id, name, modifiedTime
        """
        service = self._get_service()
        
        # Build query
        query_parts = ["mimeType = 'application/vnd.google-apps.folder'"]
        
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        
        if name_contains:
            query_parts.append(f"name contains '{name_contains}'")
        
        query = " and ".join(query_parts)
        
        results = []
        page_token = None
        
        while True:
            response = service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, modifiedTime, parents)',
                pageToken=page_token,
                orderBy='name',
            ).execute()
            
            results.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            
            if not page_token:
                break
        
        return results
    
    def list_month_folders(self, root_folder_id: str = None) -> List[Dict[str, Any]]:
        """
        List month folders (e.g., "12. Dec", "11. Nov") from the configured root.
        
        Args:
            root_folder_id: Override the configured root folder ID
            
        Returns:
            List of month folder dicts sorted by name descending
        """
        folder_id = root_folder_id or Config.GOOGLE_DRIVE_FOLDER_ID
        
        if not folder_id:
            logger.warning("GOOGLE_DRIVE_FOLDER_ID not configured")
            return []
        
        folders = self.list_folders(parent_id=folder_id)
        
        # Filter to month folders (pattern: "NN. Mon" like "12. Dec")
        import re
        month_pattern = re.compile(r'^\d{1,2}\.\s*[A-Za-z]+')
        
        month_folders = [
            f for f in folders 
            if month_pattern.match(f.get('name', ''))
        ]
        
        # Sort by name descending (most recent first)
        month_folders.sort(key=lambda x: x.get('name', ''), reverse=True)
        
        return month_folders
    
    def list_files(
        self, 
        folder_id: str, 
        file_types: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List files in a folder.
        
        Args:
            folder_id: Folder ID to list files from
            file_types: List of extensions to filter (e.g., ['pdf', 'xlsx'])
            
        Returns:
            List of file dicts with id, name, mimeType, size, modifiedTime
        """
        service = self._get_service()
        
        # Build query
        query_parts = [f"'{folder_id}' in parents"]
        
        if file_types:
            mime_queries = []
            for ext in file_types:
                if ext.lower() == 'pdf':
                    mime_queries.append("mimeType = 'application/pdf'")
                elif ext.lower() in ('xlsx', 'xls'):
                    mime_queries.append("mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'")
                    mime_queries.append("mimeType = 'application/vnd.ms-excel'")
            
            if mime_queries:
                query_parts.append(f"({' or '.join(mime_queries)})")
        
        query = " and ".join(query_parts)
        
        results = []
        page_token = None
        
        while True:
            response = service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
                pageToken=page_token,
                orderBy='name',
            ).execute()
            
            results.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            
            if not page_token:
                break
        
        return results
    
    def find_reconciliation_files(
        self, 
        folder_id: str
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Find bank PDF and Yardi Excel files in a month folder.
        
        Args:
            folder_id: Month folder ID
            
        Returns:
            Tuple of (bank_pdf_file, yardi_excel_file) - either can be None
        """
        files = self.list_files(folder_id, file_types=['pdf', 'xlsx', 'xls'])
        
        bank_pdf = None
        yardi_excel = None
        
        for f in files:
            name_lower = f.get('name', '').lower()
            
            # Bank PDF patterns: "--- SS of Madison", "Notre Dame", etc.
            if f.get('mimeType') == 'application/pdf':
                if 'notre dame' in name_lower or 'ss of' in name_lower or 'bank' in name_lower:
                    bank_pdf = f
            
            # Yardi Excel patterns: "Bank_Rec", "Bank Rec", etc.
            if 'spreadsheet' in f.get('mimeType', '').lower():
                if 'bank' in name_lower and 'rec' in name_lower:
                    yardi_excel = f
        
        return bank_pdf, yardi_excel
    
    def download_file(self, file_id: str, local_path: Path) -> bool:
        """
        Download a file from Google Drive.
        
        Args:
            file_id: File ID to download
            local_path: Local path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        service = self._get_service()
        
        try:
            request = service.files().get_media(fileId=file_id)
            
            # Ensure parent directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(local_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
            
            logger.info(f"Downloaded {local_path.name} ({local_path.stat().st_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return False
    
    def download_to_memory(self, file_id: str) -> Optional[bytes]:
        """
        Download a file from Google Drive to memory.
        
        Args:
            file_id: File ID to download
            
        Returns:
            File contents as bytes, or None on failure
        """
        service = self._get_service()
        
        try:
            request = service.files().get_media(fileId=file_id)
            
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            buffer.seek(0)
            return buffer.read()
            
        except Exception as e:
            logger.error(f"Failed to download file {file_id} to memory: {e}")
            return None


# Singleton instance
_gdrive_client: Optional[GoogleDriveClient] = None


def get_gdrive_client() -> GoogleDriveClient:
    """Get the Google Drive client singleton."""
    global _gdrive_client
    if _gdrive_client is None:
        _gdrive_client = GoogleDriveClient()
    return _gdrive_client
