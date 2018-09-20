import os
from datetime import datetime
import logging
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from flask import (
    Blueprint,
    request,
    current_app,
    send_from_directory)
from flask_cors import cross_origin
from geonature.utils.utilssqlalchemy import (
    json_resp, to_json_resp, to_csv_resp)
from geonature.utils.filemanager import removeDisallowedFilenameChars
from pypnusershub.db.tools import InsufficientRightsError
from pypnusershub import routes as fnauth

from .repositories import ExportRepository, EmptyDataSetError


logger = current_app.logger
logger.setLevel(logging.DEBUG)

blueprint = Blueprint('exports', __name__)

ASSETS = os.path.join(blueprint.root_path, 'assets')
# extracted from dummy npm install
SWAGGER_UI_DIST_DIR = os.path.join(ASSETS, 'swagger-ui-dist')
SWAGGER_API_YAML = 'api.yaml'

SHAPEFILES_DIR = os.path.join(current_app.static_folder, 'shapefiles')

DEFAULT_SCHEMA = 'gn_exports'


@blueprint.route('/swagger-ui/')
def swagger_ui():
    return send_from_directory(SWAGGER_UI_DIST_DIR, 'index.html')


@blueprint.route('/swagger-ui/<asset>')
def swagger_assets(asset):
    return send_from_directory(SWAGGER_UI_DIST_DIR, asset)


@blueprint.route('/api.yml')
def swagger_api_yml():
    return send_from_directory(ASSETS, SWAGGER_API_YAML)


def export_filename(export):
    return '_'.join([
        removeDisallowedFilenameChars(export.get('label')),
        datetime.now().strftime('%Y_%m_%d_%Hh%Mm%S')])


@blueprint.route('/<int:id_export>/<format>', methods=['GET'])
@cross_origin(
    supports_credentials=True,
    allow_headers=['content-type', 'content-disposition'],
    expose_headers=['Content-Type', 'Content-Disposition', 'Authorization'])
# @fnauth.check_auth(2, True)
def export(id_export, format, id_role=1):
    if id_export < 1:
        return to_json_resp({'api_error': 'InvalidExport'}, status=404)

    try:
        assert format in {'csv', 'json', 'shp'}
        repo = ExportRepository()
        export, columns, data = repo.get_by_id(
            id_role, id_export, with_data=True, format=format)
        if export:
            fname = export_filename(export)
            has_geometry = export.get('geometry_field', None)

            if format == 'json':
                return to_json_resp(
                    data.get('items', []),
                    as_file=True,
                    filename=fname,
                    indent=4)

            if format == 'csv':
                return to_csv_resp(
                    fname,
                    data.get('items'),
                    [c.name for c in columns],
                    separator=',')

            if (format == 'shp' and has_geometry):
                from geojson.geometry import Point, Polygon, MultiPolygon
                from geonature.utils.utilsgeometry import FionaShapeService as ShapeService  # noqa: E501
                from geonature.utils import filemanager

                filemanager.delete_recursively(
                    SHAPEFILES_DIR, excluded_files=['.gitkeep'])

                ShapeService.create_shapes_struct(
                    db_cols=columns, srid=export.get('geometry_srid'),
                    dir_path=SHAPEFILES_DIR, file_name=fname)

                items = data.get('items')
                for feature in items['features']:
                    geom, props = (feature.get(field)
                                   for field in ('geometry', 'properties'))
                    if isinstance(geom, Point):
                        ShapeService.point_shape.write(feature)
                        ShapeService.point_feature = True

                    elif (isinstance(geom, Polygon)
                          or isinstance(geom, MultiPolygon)):  # noqa: E123 W503
                        ShapeService.polygone_shape.write(props)
                        ShapeService.polygon_feature = True

                    else:
                        ShapeService.polyline_shape.write(props)
                        ShapeService.polyline_feature = True

                ShapeService.save_and_zip_shapefiles()

                return send_from_directory(
                    SHAPEFILES_DIR, fname + '.zip', as_attachment=True)
            else:
                return to_json_resp(
                    {'api_error': 'NonTransformableError'}, status=404)

    except NoResultFound as e:
        return to_json_resp({'api_error': 'NoResultFound',
                             'message': str(e)}, status=404)
    except InsufficientRightsError:
        return to_json_resp(
            {'api_error': 'InsufficientRightsError'}, status=403)
    except EmptyDataSetError as e:
        return to_json_resp(
            {'api_error': 'EmptyDataSetError',
             'message': str(e)}, status=404)
    except Exception as e:
        logger.critical('%s', e)
        # raise
        return to_json_resp({'api_error': 'LoggedError'}, status=400)


@blueprint.route('/<int:id_export>', methods=['POST'])
@fnauth.check_auth(1, True)
@json_resp
def update(id_export, id_role):
    payload = request.get_json()
    label = payload.get('label', None)
    view_name = payload.get('view_name', None)
    schema_name = payload.get('schema_name', DEFAULT_SCHEMA)
    desc = payload.get('desc', None)

    if not all(label, schema_name, view_name, desc):
        return {
            'api_error': 'MissingParameter',
            'message': 'Missing parameter: {}'. format(
                'label' if not label else 'view name' if not view_name else 'desc')}, 400  # noqa: E501

    repo = ExportRepository()
    try:
        export = repo.update(
            id_export=id_export,
            label=label,
            schema_name=schema_name,
            view_name=view_name,
            desc=desc)
    except NoResultFound as e:
        logger.warn('%s', e)
        return {'api_error': 'NoResultFound',
                'message': str(e)}, 404
    except Exception as e:
        logger.critical('%s', e)
        return {'api_error': 'LoggedError'}, 400
    else:
        return export.as_dict(), 201


@blueprint.route('/<int:id_export>', methods=['DELETE'])
@fnauth.check_auth(3, True)
@json_resp
def delete_export(id_export, id_role):
    repo = ExportRepository()
    try:
        repo.delete(id_role, id_export)
    except NoResultFound as e:
        logger.warn('%s', str(e))
        return {'api_error': 'NoResultFound',
                'message': str(e)}, 404
    except Exception as e:
        logger.critical('%s', str(e))
        return {'api_error': 'LoggedError'}, 400
    else:
        # return '', 204 -> 404 client side, interceptors ?
        return {'result': 'success'}, 204


@blueprint.route('/', methods=['POST'])
@fnauth.check_auth(1, True)
@json_resp
def create(id_role):
    payload = request.get_json()
    label = payload.get('label', None)
    view_name = payload.get('view_name', None)
    schema_name = payload.get('schema_name', DEFAULT_SCHEMA)
    desc = payload.get('desc', None)
    geometry_field = payload.get('geometry_field'),
    geometry_srid = payload.get('geometry_srid')

    # ERROR_UNKNOWN_FIELD = "unknown field"
    # ERROR_REQUIRED_FIELD = "required field"
    # from marshmallow import Schema, fields, ValidationError
    #
    # def must_not_be_blank(data):
    #     if not data:
    #         raise ValidationError('Data not provided.')
    #
    # class ExportSchema(Schema):
    #     id = fields.Integer(dump_only=True)
    #     label = fields.String(required=True, validate=[must_not_be_blank])
    #     view_name = fields.String(required=True, validate=[must_not_be_blank])
    #     schema_name = fields.String(required=True)
    #     desc = fields.String(required=False)
    #     geometry_field = fields.Geometry(required=False),
    #     geometry_srid = fields.Integer(required=False)
    #
    # export_schema = ExportSchema()
    # exportsSchema = ExportSchema(many=True)
    # # , only=('label', 'view_name', 'schema_name', 'desc')
    #
    # try:
    #     data, errors = export_schema.load(request.get_json())
    # except ValidationError as e:
    #     return jsonify(e.messages), 400

    if not(label and schema_name and view_name):
        return {
            'error': 'MissingParameter',
            'message': 'Missing parameter: {}'. format(
                'label' if not label else 'view name' if not view_name else 'desc')}, 400  # noqa: E501

    repo = ExportRepository()
    try:
        export = repo.create({
            'label': label,
            'schema_name': schema_name,
            'view_name': view_name,
            'desc': desc,
            'geometry_field': geometry_field,
            'geometry_srid': geometry_srid})
    except IntegrityError as e:
        if '(label)=({})'.format(label) in str(e):
            return {'api_error': 'RegisteredLabel',
                    'message': 'Label {} is already registered.'.format(label)}, 400  # noqa: E501
        else:
            logger.critical('%s', str(e))
            raise
    else:
        return export.as_dict(), 201


@blueprint.route('/', methods=['GET'])
# @fnauth.check_auth(2, True)
@json_resp
def getExports(id_role=1):
    repo = ExportRepository()
    try:
        exports = repo.list()
        logger.debug(exports)
    except NoResultFound:
        return {'api_error': 'NoResultFound',
                'message': 'Configure one or more export'}, 404
    except Exception as e:
        logger.critical('%s', str(e))
        return {'api_error': 'LoggedError'}, 400
    else:
        return [export.as_dict() for export in exports]


@blueprint.route('/Collections/')
@json_resp
def getCollections():
    repo = ExportRepository()
    return repo.getCollections()


@blueprint.route('/testview')
def test_view():
    from sqlalchemy.sql import Selectable as Selectable
    # from sqlalchemy.sql.expression import select
    from geonature.utils.env import DB
    from .utils.views import mkView
    from .utils.query import ExportQuery
    # from geonature.utils.utilssqlalchemy import GenericQuery

    filters = None
    # filters = [
    #     ('dateDebut', 'GREATER_OR_EQUALS', datetime(2017, 1, 1, 0, 0, 0))
    #     ]
    # -> datetime.strptime(value[0], '%Y-%m-%dT%H:%M:%S.%fZ').date()
    persisted = True
    view_model_name = 'StuffView'

    metadata = DB.MetaData(schema=DEFAULT_SCHEMA, bind=DB.engine)

    def create_view(name: str, selectable: Selectable) -> DB.Model:
        model = mkView(name, metadata, selectable)
        metadata.create_all()
        return model

    try:
        models = [m for m in DB.Model._decl_class_registry.values()
                  if hasattr(m, '__name__')]
        # from random import choice
        # random_model = choice(models)
        # while random_model.__name__ in ['LAreas']:
        #     random_model = choice(models)
        # logger.debug('model: %s', random_model.__name__)
        # selectable = select([random_model])

        # columns = request.get_json('columns')
        # selectable = select([column(c) for c in columns]).\
        #     select_from(some_table)
        # selectable = DB.session.query(random_model.__table__).selectable
        # src_model = [m for m in models if m.__name__ == 'BibNoms'][0]
        src_model = [m for m in models if m.__name__ == 'TaxrefProtectionEspeces'][0]  # noqa: E501
        # selectable = DB.session.query(src_model).selectable
        # selectable = select([src_model])
        # .where(src_model.nom_francais=='Cicindela hybrida').compile().params
        # => literals ?
        # =>join with where clause

        # select model otherwise stuff_view might end up with no pk
        # selectable = select([src_model.__table__.c.nom_francais_cite])\
        # selectable = select([src_model])\
        #     .where(src_model.__table__.c.nom_francais_cite == DB.bindparam('nom'))
        # .bindparams(nom='canard siffleur')

        # DB.bindparam('canard', type_=DB.String) + DB.text("'%'")).compile().params)

        # selectable = select([src_model])\
        #     .where(
        #         DB.and_(
        #             src_model.nom_francais_cite.isnot(None),
        #             src_model.precisions.isnot(None)))

        # .where(src_model.nom_francais_cite.like(
        #     DB.bindparam('canard', type_=DB.String) + DB.text("'%'")))

        # selectable = select([src_model]).where(
        #     DB.and_(
        #         src_model.nom_francais_cite.like('canard%'),
        #         src_model.precisions.isnot(None)))

        # # try labels
        selectable = DB.session\
                       .query(src_model)\
                       .filter(DB.and_(
                           src_model.nom_francais_cite.isnot(None),
                           src_model.precisions.isnot(None))).selectable

        if persisted and view_model_name:
            logger.debug('selectable: %s', selectable)
            model = create_view(view_model_name, selectable)

            # q = GenericQuery(
            q = ExportQuery(
                1,
                DB.session,
                model.__tablename__,
                model.__table__.schema,
                geometry_field=None,
                filters=filters,
                # filters={'filter_n_up_id_nomenclature': 1},
                limit=1000, offset=0)
            return to_json_resp({
                'model': src_model.__name__, **q.return_query()})
    except Exception as e:
        logger.critical('error: %s', str(e))
        raise
        return to_json_resp({'error': str(e),
                             'model': src_model.__name__}, status=400)

# model: LAreas
# TypeError(b"\x01\x06\x00\x00 j\x08\x00\x00\x01\x00
# [...]
# \x01\x03\x00\x00\x00|\xbf+A\x00\x00\x00@MBZA" is not JSON serializable
