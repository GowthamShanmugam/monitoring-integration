import copy
import json
import os

from tendrl.commons.utils import log_utils as logger
from tendrl.monitoring_integration.grafana import constants
from tendrl.monitoring_integration.grafana import utils


def set_alert(panel, alert_thresholds, panel_title, resource_name):
    panel["thresholds"] = [{"colorMode": "critical", "fill": True,
                            "line": True,
                            "op": "gt",
                            "value": alert_thresholds[panel_title]["Warning"]}]
    panel["alert"] = (
        {"conditions": [
            {"evaluator": {"params": [alert_thresholds[
                panel_title]["Warning"]], "type": "gt"},
             "operator": {"type": "and"},
             "query": {"params": [panel["targets"][-1]["refId"], "3m", "now"]},
             "reducer": {"params": [], "type": "avg"},
             "type": "query"
             }],
         "executionErrorState": "keep_state",
         "frequency": "60s", "handler": 1,
         "name": str(resource_name) + " " + str(panel["title"]) + " Alert",
         "noDataState": "keep_state",
         "notifications": []
         }
    )


def get_panels(resource_rows):

    new_resource_panels = []
    try:
        for row in resource_rows:
            panels = row["panels"]
            for panel in panels:
                if panel["type"] == "graph":
                    new_resource_panels.append(copy.deepcopy(panel))
    except (KeyError, AttributeError) as ex:
        logger.log("error", NS.get("publisher_id", None),
                   {'message': "Error in retrieving resource "
                   "rows (get_panels) " + str(ex)})
    return new_resource_panels


def set_gluster_target(target, integration_id, resource, resource_name):

    target["target"] = target["target"].replace('$interval', '1m')
    target["target"] = target["target"].replace('$my_app', 'tendrl')
    target["target"] = target["target"].replace(
        '$cluster_id', str(integration_id))
    if resource_name == "volumes":
        target["target"] = target["target"].replace('$volume_name',
                                                    str(resource["name"]))
        new_title = str(resource["name"])
    elif resource_name == "hosts":
        target["target"] = target["target"].replace(
            '$host_name',
            str(resource["fqdn"].replace(".", "_")))
        new_title = str(resource["fqdn"].replace(".", "_"))
    elif resource_name == "bricks":
        target["target"] = target["target"].replace(
            '$host_name',
            str(resource["hostname"].replace(".", "_")))
        target["target"] = target["target"].replace(
            '$brick_path',
            str(resource["brick_path"]))
        target["target"] = target["target"].replace('$volume_name',
                                                    str(resource["vol_name"]))
        new_title = str(resource["vol_name"] + "-" + resource[
            "hostname"].replace(".", "_")) + \
            "-" + str(resource["brick_path"])
    if "alias" in target["target"] and "aliasByNode" not in target["target"]:
        target["target"] = target["target"].split('(', 1)[-1].rsplit(',', 1)[0]
    return new_title


def create_resource_dashboard(resource_name, resource):
    sds_name = resource['sds_name']
    integration_id = resource['integration_id']
    dashboard_path = constants.PATH_PREFIX + constants.DASHBOARD_PATH + \
        "/tendrl-" + str(sds_name) + "-" + str(resource_name) + '.json'

    if os.path.exists(dashboard_path):
        resource_file = utils.fread(dashboard_path)
        try:
            new_title = ""
            resource_json = json.loads(resource_file)
            resource_json["dashboard"]["title"] = "Alerts - " + \
                str(resource_json["dashboard"]["title"])
            resource_rows = resource_json["dashboard"]["rows"]
            global_row = {"collapse": False,
                          "height": 250,
                          "panels": [],
                          "repeat": None,
                          "repeatIteration": None,
                          "repeatRowId": None,
                          "showTitle": False,
                          "title": "Dashboard Row",
                          "titleSize": "h6"
                          }
            new_resource_panels = get_panels(resource_rows)
            alert_thresholds = NS.monitoring.definitions.get_parsed_defs()[
                "namespace.monitoring"]["thresholds"][resource_name]
            all_resource_rows = []
            count = 1
            global_row["panels"] = []
            panel_count = 1
            for panel in new_resource_panels:
                try:
                    new_title = ""
                    for panel_title in alert_thresholds:
                        if not panel["title"].lower().find(
                                panel_title.replace("_", " ")):
                            targets = panel["targets"]
                            for target in targets:
                                if sds_name == constants.GLUSTER:
                                    new_title = set_gluster_target(
                                        target,
                                        integration_id,
                                        resource,
                                        resource_name
                                    )
                                else:
                                    # In future need to add ceph target
                                    pass
                            set_alert(
                                panel,
                                alert_thresholds,
                                panel_title,
                                resource_name
                            )
                            panel["id"] = count
                            panel["legend"]["show"] = False
                            panel["title"] = panel["title"] + \
                                " - " + str(new_title)
                            count = count + 1
                            panel_count = panel_count + 1
                            # For better visibility,
                            # 7 panels per row is created
                            if panel_count < constants.MAX_PANELS_IN_ROW:
                                global_row["panels"].append(panel)
                            else:
                                global_row["panels"].append(panel)
                                all_resource_rows.append(
                                    copy.deepcopy(global_row))
                                global_row["panels"] = []
                                panel_count = 1
                except KeyError as ex:
                    logger.log(
                        "debug",
                        NS.get("publisher_id", None),
                        {'message': str(panel[
                            "title"]) + "failed" + str(ex)}
                    )
            all_resource_rows.append(copy.deepcopy(global_row))
            resource_json["dashboard"]["rows"] = []
            resource_json["dashboard"]["rows"] = all_resource_rows
            resource_json["dashboard"]["templating"] = {}
            return resource_json
        except Exception as ex:
            logger.log("error", NS.get("publisher_id", None),
                       {'message': str(ex)})


def add_panel(resources, resource_type, alert_dashboard, most_recent_panel_id):
    for resource in resources:
        sds_name = resource["sds_name"]
        integration_id = resource["integration_id"]
        resource_name = resource["resource_name"]
        try:
            if sds_name == constants.GLUSTER:
                alert_rows = fetch_rows(alert_dashboard)
                add_gluster_resource_panel(
                    alert_rows,
                    integration_id,
                    resource_type,
                    resource_name,
                    most_recent_panel_id
                )
                alert_dashboard = create_updated_dashboard(
                    alert_dashboard, alert_rows
                )
                most_recent_panel_id = alert_rows[-1]["panels"][-1]["id"]
        except Exception as ex:
            logger.log("error", NS.get("publisher_id", None),
                       {'message': "Error while updating "
                        "dashboard for %s" % resource_name})
            raise ex
    return alert_dashboard


def check_duplicate(
    resource_json, resources, resource_type
):
    # Keeping rows which are match with newly collcted cluster details
    alert_dashboard = copy.deepcopy(resource_json)
    resource_json["dashboard"]["rows"] = []
    new_resource = []
    most_recent_panel_id = 1
    for resource in resources:
        new_resource_flag = True
        integration_id = str(resource["integration_id"])
        for row in alert_dashboard["dashboard"]["rows"]:
            if "panels" in row:
                for target in row["panels"][0]["targets"]:
                    resource_name = str(resource["resource_name"])
                    if resource_type == "bricks":
                        hostname = resource_name.split(":")[0].split(
                            "|")[1].replace(".", "_")
                        resource_name = "." + resource_name.split(
                            ":", 1)[1].replace("/", "|") + "."
                    if resource_name is not None:
                        if integration_id in target["target"] and \
                                resource_name in target["target"]:
                            if resource_type == "bricks":
                                if hostname in target["target"]:
                                    resource_json["dashboard"]["rows"].append(
                                        row
                                    )
                                    new_resource_flag = False
                                    break
                            else:
                                resource_json["dashboard"]["rows"].append(
                                    row
                                )
                                new_resource_flag = False
                                break
                    elif integration_id in target["target"]:
                        resource_json["dashboard"]["rows"].append(
                            row
                        )
                        new_resource_flag = False
                        break
            else:
                break
            if most_recent_panel_id < row["panels"][-1]["id"]:
                most_recent_panel_id = row["panels"][-1]["id"]
        if new_resource_flag:
            new_resource.append(resource)
    return new_resource, resource_json, most_recent_panel_id


def add_gluster_resource_panel(
    alert_rows, cluster_id, resource_type, resource_name, most_recent_panel_id
):
    if resource_type == "hosts":
            resource_type = "nodes"
    panel_count = most_recent_panel_id
    for alert_row in alert_rows:
        panel_count += 1
        for panel in alert_row["panels"]:
            targets = panel["targets"]
            for target in targets:
                try:
                    if resource_type == "bricks":
                        panel_target = ("tendrl" + target["target"].split(
                            "tendrl")[1].split(")")[0]).split(".")
                        old_cluster_id = panel_target[
                            panel_target.index("clusters") + 1]
                        target["target"] = target["target"].replace(
                            old_cluster_id, str(cluster_id))
                        if "volumes" in panel_target:
                            old_resource_name = panel_target[
                                panel_target.index("volumes") + 1]
                            target["target"] = target["target"].replace(
                                old_resource_name,
                                str(resource_name.split("|", 1)[0]))
                        if "nodes" in panel_target:
                            old_resource_name = panel_target[
                                panel_target.index("nodes") + 1]
                            target["target"] = target["target"].replace(
                                old_resource_name,
                                str(resource_name.split("|", 1)[1].split(
                                    ":", 1)[0].replace(".", "_")))
                        if "bricks" in panel_target:
                            old_resource_name = panel_target[
                                panel_target.index("bricks") + 1]
                            target["target"] = target["target"].replace(
                                old_resource_name,
                                str(resource_name.split("|", 1)[1].split(
                                    ":", 1)[1].replace("/", "|")))
                    else:
                        panel_target = ("tendrl" + target["target"].split(
                            "tendrl")[1].split(")")[0]).split(".")
                        old_cluster_id = panel_target[
                            panel_target.index("clusters") + 1]
                        target["target"] = target["target"].replace(
                            old_cluster_id, str(cluster_id))
                        if resource_name is not None:
                            old_resource_name = panel_target[
                                panel_target.index(str(resource_type)) + 1]
                            target["target"] = target["target"].replace(
                                old_resource_name, str(resource_name))
                except (KeyError, IndexError):
                    pass
            panel["id"] = panel_count
            panel_count = panel_count + 1
            new_title = resource_name
            if resource_type == "bricks":
                host_name = resource_name.split("|", 1)[1].split(
                    ":", 1)[0].replace(".", "_")
                brick_name = resource_name.split("|", 1)[1].split(
                    ":", 1)[1].replace("/", "|")
                volume_name = resource_name.split("|", 1)[0]
                new_title = volume_name + "|" + host_name + ":" + brick_name
            panel["title"] = panel["title"].split(
                "-", 1)[0] + "-" + str(new_title)


def fetch_rows(dashboard_json):

    rows = dashboard_json["dashboard"]["rows"]
    if len(rows) > 1:
        for count in xrange(1, len(rows)):
            if rows[0]["panels"][0]["title"].split("-", 1)[0] == \
                    rows[count]["panels"][0]["title"].split("-", 1)[0]:
                alert_row = copy.deepcopy(
                    dashboard_json["dashboard"]["rows"][:count])
                break
    else:
        alert_row = [copy.deepcopy(dashboard_json["dashboard"]["rows"][-1])]
    return alert_row


def create_updated_dashboard(dashboard_json, alert_rows):
    dashboard_json["dashboard"]["rows"] = dashboard_json[
        "dashboard"]["rows"] + alert_rows
    return dashboard_json
