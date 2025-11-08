# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    openai_enabled = fields.Boolean(string='Habilitar OpenAI Chat', config_parameter='openai_chat.enabled')
    openai_api_key = fields.Char(string='OpenAI API Key', config_parameter='openai_chat.api_key')
    openai_organization = fields.Char(string='OpenAI Organization', config_parameter='openai_chat.organization')
    openai_base_url = fields.Char(string='OpenAI Base URL', default='https://api.openai.com/v1', config_parameter='openai_chat.base_url')
    openai_model = fields.Char(string='Modelo', default='gpt-4o-mini', config_parameter='openai_chat.model')
    openai_temperature = fields.Float(string='Temperature', default=0.2, config_parameter='openai_chat.temperature')
    openai_context_count = fields.Integer(string='Contexto (mensajes)', default=10, config_parameter='openai_chat.context_count')
    openai_timeout = fields.Integer(string='Timeout (s)', default=60, config_parameter='openai_chat.timeout')
    openai_system_prompt = fields.Char(string='System prompt', config_parameter='openai_chat.system_prompt', help='Prompt del sistema para OpenAI')

    def action_test_openai(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('openai_chat.api_key')
        base_url = (ICP.get_param('openai_chat.base_url') or 'https://api.openai.com/v1').rstrip('/')
        model = ICP.get_param('openai_chat.model') or 'gpt-4o-mini'
        temperature = float(ICP.get_param('openai_chat.temperature') or 0.2)
        system_prompt = ICP.get_param('openai_chat.system_prompt') or 'Eres un asistente útil para usuarios de Odoo.'
        timeout = int(ICP.get_param('openai_chat.timeout') or 60)

        if not api_key:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'OpenAI', 'message': 'Falta API Key', 'type': 'danger', 'sticky': False}
            }

        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Responde con la palabra OK."},
            ],
        }
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
            if resp.ok:
                content = resp.json()['choices'][0]['message']['content']
                msg = f"Conexión correcta: {content[:120]}"
                t = 'success'
            else:
                msg = f"Error {resp.status_code}: {resp.text[:200]}"
                t = 'danger'
        except Exception as e:
            msg = f"Excepción: {e}"
            t = 'danger'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'OpenAI', 'message': msg, 'type': t, 'sticky': False}
        }

    openai_enabled = fields.Boolean(
        string='Habilitar OpenAI en Discuss',
        config_parameter='openai_chat.enabled',
    )
    openai_api_key = fields.Char(
        string='OpenAI API Key',
        help='Se almacenará en parámetros del sistema',
        config_parameter='openai_chat.api_key',
        groups='base.group_system'
    )
    openai_organization = fields.Char(
        string='OpenAI Organization (opcional)',
        config_parameter='openai_chat.organization',
        groups='base.group_system'
    )
    openai_base_url = fields.Char(
        string='OpenAI Base URL',
        default='https://api.openai.com/v1',
        help='Cambiar si usas un proxy o Azure (compatible con API de OpenAI)',
        config_parameter='openai_chat.base_url'
    )
    openai_model = fields.Char(
        string='Modelo por defecto',
        default='gpt-4o-mini',
        help='Ejemplo: gpt-4o-mini, gpt-4.1-mini',
        config_parameter='openai_chat.model'
    )
    openai_temperature = fields.Float(
        string='Temperatura',
        default=0.2,
        config_parameter='openai_chat.temperature'
    )
    openai_context_count = fields.Integer(
        string='Mensajes de contexto',
        default=10,
        help='Cantidad de mensajes recientes del canal a enviar como contexto',
        config_parameter='openai_chat.context_count'
    )
    openai_system_prompt = fields.Char(
        string='Prompt de sistema',
        default='Eres un asistente útil para usuarios de Odoo. Responde de forma breve y clara.',
        config_parameter='openai_chat.system_prompt'
    )
    openai_timeout = fields.Integer(
        string='Timeout (segundos)',
        default=60,
        config_parameter='openai_chat.timeout'
    )

    @api.onchange('openai_base_url')
    def _onchange_openai_base_url(self):
        if self.openai_base_url:
            self.openai_base_url = self.openai_base_url.rstrip('/')
