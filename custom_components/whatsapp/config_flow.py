"""Config flow for WhatsApp."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .client import BridgeAuthError, BridgeError, async_probe
from .const import (
    CONF_DEFAULT_CHAT,
    CONF_HOST,
    CONF_MAX_AGE,
    CONF_OWN_MESSAGES,
    CONF_TOKEN,
    DEFAULT_HOST,
    DOMAIN,
    OWN_MESSAGES_MODES,
    OWN_MESSAGES_OFF,
)
from .helpers import normalize_chat_id

_LOGGER = logging.getLogger(__name__)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class WhatsAppConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the connection to the wa-bridge add-on."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> WhatsAppOptionsFlow:
        return WhatsAppOptionsFlow()

    async def _validate(self, url: str, token: str) -> dict[str, str]:
        try:
            await async_probe(self.hass, url, token)
        except BridgeAuthError:
            return {"base": "invalid_auth"}
        except BridgeError as err:
            _LOGGER.warning("Cannot reach the WhatsApp bridge at %s: %s", url, err)
            return {"base": "cannot_connect"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup: bridge URL and token."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate(user_input[CONF_HOST], user_input[CONF_TOKEN])
            if not errors:
                return self.async_create_entry(title="WhatsApp", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                        vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_hassio(
        self, discovery_info: HassioServiceInfo
    ) -> ConfigFlowResult:
        """Discovery by the wa-bridge add-on (host, port and token)."""
        config = discovery_info.config
        url = f"ws://{config['host']}:{config['port']}"
        data = {CONF_HOST: url, CONF_TOKEN: config["token"]}
        await self.async_set_unique_id(DOMAIN)
        # An existing entry follows the add-on (new token, new hostname).
        self._abort_if_unique_id_configured(updates=data)
        self._discovered = data
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the add-on discovered by the Supervisor."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate(
                self._discovered[CONF_HOST], self._discovered[CONF_TOKEN]
            )
            if not errors:
                return self.async_create_entry(title="WhatsApp", data=self._discovered)
        return self.async_show_form(step_id="hassio_confirm", errors=errors)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The bridge rejected the token, or the entry has none yet."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the bridge's current token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate(entry.data[CONF_HOST], user_input[CONF_TOKEN])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )


class WhatsAppOptionsFlow(OptionsFlowWithReload):
    """Default chat for notify and own messages."""

    def _own_chat_id(self) -> str | None:
        """The linked account's own chat, if the bridge has reported it."""
        entry = self.config_entry
        if entry.state is not ConfigEntryState.LOADED:
            return None
        phone = entry.runtime_data.status.get("phone")
        return f"{phone}@c.us" if phone else None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(user_input)
            data[CONF_MAX_AGE] = int(data.get(CONF_MAX_AGE) or 0)
            if raw := (data.get(CONF_DEFAULT_CHAT) or "").strip():
                try:
                    data[CONF_DEFAULT_CHAT] = normalize_chat_id(
                        raw, self.hass.config.country
                    )
                except ValueError:
                    errors[CONF_DEFAULT_CHAT] = "invalid_chat_id"
                else:
                    # A message to yourself does not notify you on the phone.
                    if data[CONF_DEFAULT_CHAT] == self._own_chat_id():
                        errors[CONF_DEFAULT_CHAT] = "own_number"
            else:
                data.pop(CONF_DEFAULT_CHAT, None)
            if not errors:
                return self.async_create_entry(data=data)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Optional(CONF_DEFAULT_CHAT): str,
                        vol.Required(
                            CONF_OWN_MESSAGES,
                            default=options.get(CONF_OWN_MESSAGES, OWN_MESSAGES_OFF),
                        ): SelectSelector(
                            SelectSelectorConfig(
                                options=OWN_MESSAGES_MODES,
                                mode=SelectSelectorMode.LIST,
                                translation_key=CONF_OWN_MESSAGES,
                            )
                        ),
                        vol.Required(
                            CONF_MAX_AGE, default=options.get(CONF_MAX_AGE, 0)
                        ): NumberSelector(
                            NumberSelectorConfig(
                                min=0,
                                max=10080,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="min",
                            )
                        ),
                    }
                ),
                user_input or options,
            ),
            errors=errors,
        )
