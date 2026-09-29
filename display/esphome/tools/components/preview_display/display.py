import esphome.codegen as cg
from esphome.components import display
import esphome.config_validation as cv
from esphome.const import CONF_HEIGHT, CONF_ID, CONF_LAMBDA, CONF_WIDTH

preview_ns = cg.esphome_ns.namespace("preview_display")
PreviewDisplay = preview_ns.class_("PreviewDisplay", display.Display)

CONFIG_SCHEMA = cv.All(
    display.FULL_DISPLAY_SCHEMA.extend(
        {
            cv.GenerateID(): cv.declare_id(PreviewDisplay),
            cv.Required(CONF_WIDTH): cv.int_range(min=1, max=4096),
            cv.Required(CONF_HEIGHT): cv.int_range(min=1, max=4096),
        }
    ).extend(cv.polling_component_schema("never")),
    cv.only_on("host"),
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID], config[CONF_WIDTH], config[CONF_HEIGHT])
    await display.register_display(var, config)
    if CONF_LAMBDA in config:
        lambda_ = await cg.process_lambda(
            config[CONF_LAMBDA], [(display.DisplayRef, "it")], return_type=cg.void
        )
        cg.add(var.set_writer(lambda_))
