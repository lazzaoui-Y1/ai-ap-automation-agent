"""
backend/app/erp_connectors/sap_sftp_xml.py
موصل SAP عبر SFTP - إرسال XML
"""

from pathlib import Path
from typing import Dict, Any
import paramiko
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

from .base_connector import BaseERPConnector, ConnectorType, ConnectorStatus, ConnectorFactory
from ..schemas.invoice_schema import Invoice
from ..utils.exceptions import ERPConnectionError, ERPAuthenticationError


class SAPSFTPXMLConnector(BaseERPConnector):
    """
    موصل SAP - رفع ملفات XML عبر SFTP
    
    الإعدادات المطلوبة:
        host: عنوان SFTP
        port: منفذ (افتراضي: 22)
        username: اسم المستخدم
        password أو private_key_path: المصادقة
        remote_path: المسار على الخادم
        xml_template: قالب XML (افتراضي: sap_xml.j2)
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any], connector_type: ConnectorType):
        super().__init__(customer_id, config, connector_type)
        
        # إعدادات SFTP
        self.host = config.get('host')
        self.port = config.get('port', 22)
        self.username = config.get('username')
        self.password = config.get('password')
        self.private_key_path = config.get('private_key_path')
        self.remote_path = config.get('remote_path', '/invoices')
        
        # XML Template
        self.template_name = config.get('xml_template', 'sap_xml.j2')
        self.template_env = Environment(loader=FileSystemLoader('./shared/templates'))
        
        # SFTP Client
        self.sftp_client = None
        self.ssh_client = None
    
    def connect(self) -> bool:
        """الاتصال بـ SFTP"""
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # المصادقة
            if self.private_key_path:
                key = paramiko.RSAKey.from_private_key_file(self.private_key_path)
                self.ssh_client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    pkey=key
                )
            else:
                self.ssh_client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password
                )
            
            self.sftp_client = self.ssh_client.open_sftp()
            self.status = ConnectorStatus.CONNECTED
            
            self._log_operation("connect", "success")
            self.logger.info(f"SAP SFTP connected: {self.host}")
            
            return True
        
        except paramiko.AuthenticationException as e:
            raise ERPAuthenticationError("sap_sftp")
        except Exception as e:
            raise ERPConnectionError(str(e), "sap_sftp")
    
    def disconnect(self) -> bool:
        """قطع الاتصال"""
        if self.sftp_client:
            self.sftp_client.close()
        if self.ssh_client:
            self.ssh_client.close()
        
        self.status = ConnectorStatus.DISCONNECTED
        return True
    
    def send_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        """إرسال فاتورة كـ XML"""
        try:
            # التحقق
            self._validate_invoice_data(invoice)
            
            # توليد XML
            template = self.template_env.get_template(self.template_name)
            xml_content = template.render(invoice=invoice, timestamp=datetime.now())
            
            # اسم الملف
            filename = f"INV_{invoice.invoice_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
            remote_file = f"{self.remote_path}/{filename}"
            
            # رفع الملف
            if not self.sftp_client:
                self.connect()
            
            with self.sftp_client.open(remote_file, 'w') as f:
                f.write(xml_content)
            
            self._update_sync_stats(success=True)
            
            return {
                "success": True,
                "erp_id": filename,
                "message": "XML uploaded via SFTP",
                "details": {"remote_path": remote_file}
            }
        
        except Exception as e:
            self._update_sync_stats(success=False)
            raise
    
    def test_connection(self) -> bool:
        """اختبار الاتصال"""
        try:
            if self.connect():
                # اختبار قراءة المجلد
                self.sftp_client.listdir(self.remote_path)
                self.disconnect()
                return True
        except:
            return False


ConnectorFactory.register(ConnectorType.SAP_SFTP_XML, SAPSFTPXMLConnector)
__all__ = ['SAPSFTPXMLConnector']