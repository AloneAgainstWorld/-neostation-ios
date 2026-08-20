from pathlib import Path

p = Path('lib/screens/library_screen/library_screen.dart')
s = p.read_text(encoding='utf-8')

old = '''  Widget _buildInlineTitleSearchHub(BuildContext context) {
    final theme = Theme.of(context);
    return CustomScrollView(
      controller: _libraryScrollController,
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: [
        SliverToBoxAdapter(child: _buildInlineTitleSearchRow(context, theme)),
        if (_titleSearchFiltersExpanded) ...[
          SliverToBoxAdapter(child: SizedBox(height: 8.r)),
          SliverToBoxAdapter(child: _buildFilters(context, includeSearch: false)),
        ],
        SliverToBoxAdapter(child: SizedBox(height: 10.r)),
        _buildNativeLibrarySliver(context, theme),
        _buildCatalogProgressSliver(context),
        SliverToBoxAdapter(child: SizedBox(height: 42.r)),
      ],
    );
  }
'''
new = '''  Widget _buildInlineTitleSearchHub(BuildContext context) {
    final theme = Theme.of(context);
    // Match the standard game-search architecture: the query band remains
    // fixed and only the results region scrolls. This also guarantees that the
    // iOS keyboard can never cover the field the user is actively typing in.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildInlineTitleSearchRow(context, theme),
        if (_titleSearchFiltersExpanded) ...[
          SizedBox(height: 8.r),
          _buildFilters(context, includeSearch: false),
        ],
        SizedBox(height: 10.r),
        Expanded(
          child: CustomScrollView(
            controller: _libraryScrollController,
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            slivers: [
              _buildNativeLibrarySliver(context, theme),
              _buildCatalogProgressSliver(context),
              SliverToBoxAdapter(child: SizedBox(height: 42.r)),
            ],
          ),
        ),
      ],
    );
  }
'''
if old not in s:
    raise SystemExit('inline search hub anchor not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('fixed inline search band')
