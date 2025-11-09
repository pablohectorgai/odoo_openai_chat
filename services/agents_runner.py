# services/agents_runner.py
# -*- coding: utf-8 -*-
import os
import asyncio
import logging

from odoo import tools, _

_logger = logging.getLogger(__name__)

def _import_agents():
    """
    pip: pip install "openai-agents @ git+https://github.com/openai/openai-agents-python.git"
    """
    try:
        from agents import (
            FileSearchTool,
            Agent,
            ModelSettings,
            Runner,
            RunConfig,
            trace,
            SQLiteSession,
        )
        from openai.types.shared.reasoning import Reasoning
        return FileSearchTool, Agent, ModelSettings, Runner, RunConfig, trace, SQLiteSession, Reasoning
    except Exception as e:
        raise RuntimeError(
            "Agents SDK no instalado. Ejecuta:\n"
            'pip install "openai-agents @ git+https://github.com/openai/openai-agents-python.git"'
        ) from e

def _build_agent(env, model=None):
    """
    Construye el agente con parámetros desde Ajustes. Si model se pasa, lo usa; si no, lee de config.
    """
    FileSearchTool, Agent, ModelSettings, Runner, RunConfig, trace, SQLiteSession, Reasoning = _import_agents()
    ICP = env['ir.config_parameter'].sudo()

    instructions = ICP.get_param('openai_chat.agent_instructions') or \
                   ICP.get_param('openai_chat.system_prompt') or \
                   'Eres un asistente experto en Odoo 17 Community y sus módulos.'
    model = model or ICP.get_param('openai_chat.agent_model') or \
            ICP.get_param('openai_chat.model') or 'gpt-4o-mini'
    vec_ids_str = ICP.get_param('openai_chat.agent_vector_store_ids') or ''
    vec_ids = [v.strip() for v in vec_ids_str.split(',') if v.strip()]

    tools_list = []
    if vec_ids:
        tools_list.append(FileSearchTool(vector_store_ids=vec_ids))

    agent = Agent(
        name="Odoo Support Agent",
        instructions=instructions,
        model=model,
        tools=tools_list,
        model_settings=ModelSettings(
            store=True,
            reasoning=Reasoning(
                effort="high",
                summary="auto",
            ),
        ),
    )
    return agent

def _run_async(coro):
    """
    Ejecuta una corrutina en un event loop propio (evita problemas si ya hay un loop).
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.stop()
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)

def run_agent_for_channel(env, channel, user_prompt):
    """
    Ejecuta el agente (Agents SDK) para un canal de Discuss.
    - Memoria por canal con SQLiteSession en filestore.
    - Pone timeout y fallback de modelo si el configurado no existe.
    - Nunca devuelve cadena vacía (si falla, devuelve un mensaje de error).
    """
    FileSearchTool, Agent, ModelSettings, Runner, RunConfig, trace, SQLiteSession, Reasoning = _import_agents()
    ICP = env['ir.config_parameter'].sudo()

    api_key = ICP.get_param('openai_chat.api_key')
    base_url = (ICP.get_param('openai_chat.base_url') or 'https://api.openai.com/v1').rstrip('/')
    timeout = int(ICP.get_param('openai_chat.timeout') or 60)
    fallback_model = 'gpt-4o-mini'  # por si el modelo configurado no está disponible

    if not api_key:
        raise ValueError('Falta API Key para Agents SDK')

    # Variables de entorno que el SDK puede leer
    os.environ['OPENAI_API_KEY'] = api_key
    os.environ['OPENAI_BASE_URL'] = base_url

    # Sesión SQLite por canal
    filestore_dir = tools.config.filestore(env.cr.dbname)
    agents_dir = os.path.join(filestore_dir, 'openai_agents')
    os.makedirs(agents_dir, exist_ok=True)
    session_path = os.path.join(agents_dir, f'channel_{channel.id}.sqlite3')
    session = SQLiteSession(session_path)

    # Entrada del usuario en formato TResponseInputItem[]
    input_items = [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": user_prompt}],
        }
    ]

    def _extract_text(result):
        # final_output_as(str) si está disponible
        text = None
        if hasattr(result, 'final_output_as'):
            try:
                text = result.final_output_as(str)
            except Exception:
                text = None
        if not text:
            text = getattr(result, 'final_output', None) or getattr(result, 'output', None)
        return str(text) if text is not None else ''

    async def _call(agent):
        with trace("Odoo Agents Run"):
            # Algunas versiones aceptan request_timeout; si no, caemos sin él
            try:
                return await Runner.run(
                    agent,
                    input=input_items,
                    session=session,
                    run_config=RunConfig(trace_metadata={
                        "__trace_source__": "odoo",
                        "channel_id": str(channel.id),
                    }),
                    request_timeout=timeout,
                )
            except TypeError:
                _logger.debug("Runner.run() no acepta request_timeout en esta versión; reintentando sin timeout kwarg")
                return await Runner.run(
                    agent,
                    input=input_items,
                    session=session,
                    run_config=RunConfig(trace_metadata={
                        "__trace_source__": "odoo",
                        "channel_id": str(channel.id),
                    }),
                )

    # 1) Intento con el modelo configurado
    try:
        agent = _build_agent(env)
        _logger.info("Agents: ejecutando modelo '%s' para canal %s", agent.model, channel.id)
        result = _run_async(_call(agent))
        text = _extract_text(result)
        if not text:
            _logger.warning("Agents: respuesta vacía para canal %s", channel.id)
            return _("No se pudo obtener respuesta del modelo.")
        return text
    except Exception as e:
        msg = str(e)
        _logger.warning("Agents: error con modelo configurado: %s", msg)

    # 2) Fallback de modelo (p.ej. cuando 'gpt-5' no está habilitado)
    try:
        agent_fb = _build_agent(env, model=fallback_model)
        _logger.info("Agents: intentando fallback con modelo '%s' para canal %s", agent_fb.model, channel.id)
        result = _run_async(_call(agent_fb))
        text = _extract_text(result)
        if not text:
            _logger.warning("Agents fallback: respuesta vacía para canal %s", channel.id)
            return _("No se pudo obtener respuesta del modelo.")
        return text
    except Exception as e2:
        _logger.exception("Agents fallback: error definitivo: %s", e2)
        return _("No se pudo obtener respuesta del modelo.")
