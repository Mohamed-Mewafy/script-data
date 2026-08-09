import { useCallback, useEffect, useRef, useState } from 'react';
import {
  useAnimes,
  useFeaturedAnimes,
  useFavorites,
  useContinueWatching,
} from '@/hooks/useData';
import { useSEO } from '@/hooks/useSEO';
import { supabase } from '@/lib/supabaseClient';
import { cleanTitle } from '@/lib/format';
import { Hero } from '@/components/Hero';
import { AnimeCard } from '@/components/AnimeCard';
import { CategoryChips } from '@/components/CategoryChips';
import { CardSkeleton } from '@/components/Skeletons';
import { useRouter } from '@/context/RouterContext';
import {
  Play,
  Flame,
  Star,
  Sparkles,
  Compass,
  Film,
  Tv,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

function mapCimaMovie(item: any): any {
  return {
    id: item.id,
    title: cleanTitle(item.title),
    media_type: 'movie',
    cover_image_url: item.poster_url,
    banner_image_url: item.poster_url,
    release_year: item.year,
    rating_average: item.rating || 0,
    rating_count: 0,
    view_count: 0,
    genres: item.genres || item.category_type || null,
    synopsis: item.description || null,
    created_at: item.created_at || new Date().toISOString(),
  };
}

function mapCimaSeries(item: any): any {
  // تنظيف العنوان وإزالة أي كلمات موسم خاطئة أو أرقام حلقات متداخلة جلبتها السكريبتات مثل "- الموسم 8"
  let rawTitle = cleanTitle(item.title);
  let cleanedTitle = rawTitle.replace(/\s*-\s*الموسم\s*\d+/g, '').trim();

  return {
    id: item.id,
    title: cleanedTitle,
    media_type: 'series',
    cover_image_url: item.poster_url,
    banner_image_url: item.poster_url,
    release_year: item.year,
    rating_average: item.rating || 0,
    rating_count: 0,
    view_count: 0,
    genres: item.genres || item.category_type || null,
    synopsis: item.description || null,
    created_at: item.created_at || new Date().toISOString(),
  };
}

const MOVIE_SECTIONS: { key: string; label: string; category: string; year: number; icon: React.ReactNode; href: string }[] = [
  { key: 'ar-2026', label: 'أفلام عربي 2026', category: 'افلام عربي', year: 2026, icon: <Film className="h-5 w-5 sm:h-6 sm:w-6 text-blue-400" />, href: '/movie-list/%D8%A7%D9%81%D9%84%D8%A7%D9%81%20%D8%B9%D8%B1%D8%A8%D9%8A/2026' },
  { key: 'en-2026', label: 'أفلام أجنبي 2026', category: 'افلام اجنبي', year: 2026, icon: <Film className="h-5 w-5 sm:h-6 sm:w-6 text-purple-400" />, href: '/movie-list/%D8%A7%D9%81%D9%84%D8%A7%D9%81%20%D8%A7%D8%AC%D9%86%D8%A8%D9%8A/2026' },
  { key: 'ramadan-2026', label: 'مسلسلات رمضان 2026', category: 'مسلسلات رمضان 2026', year: 2026, icon: <Film className="h-5 w-5 sm:h-6 sm:w-6 text-blue-400" />, href: '/movie-list/%D9%85%D8%B3%D9%84%D8%B3%D9%84%D8%A7%D8%AA%20%D8%B1%D9%85%D8%B6%D8%A7%D9%86/2026' },
  { key: 'ar-2025', label: 'أفلام عربي 2025', category: 'افلام عربي', year: 2025, icon: <Film className="h-5 w-5 sm:h-6 sm:w-6 text-cyan-400" />, href: '/movie-list/%D8%A7%D9%81%D9%84%D8%A7%D9%81%20%D8%B9%D8%B1%D8%A8%D9%8A/2025' },
  { key: 'en-2025', label: 'أفلام أجنبي 2025', category: 'افلام اجنبي', year: 2025, icon: <Film className="h-5 w-5 sm:h-6 sm:w-6 text-amber-400" />, href: '/movie-list/%D8%A7%D9%81%D9%84%D8%A7%D9%81%20%D8%A7%D8%AC%D9%86%D8%A8%D9%8A/2025' },
];

const hideScrollbarStyle = {
  overflowX: 'auto' as const,
  overflowY: 'hidden' as const,
  scrollbarWidth: 'none' as const,
  msOverflowStyle: 'none' as const,
  WebkitOverflowScrolling: 'touch' as const,
};

export function HomePage() {
  const { animes: recentAnimes, loading: recentAnimesLoading } = useAnimes({ orderBy: 'created_at', limit: 10 });
  const { animes: popularAnimes, loading: popularAnimesLoading } = useAnimes({ orderBy: 'view_count', limit: 10 });
  const { animes: topRatedAnimes, loading: topRatedAnimesLoading } = useAnimes({ orderBy: 'rating_average', limit: 10 });

  const [heroItems, setHeroItems] = useState<any[]>([]);
  const [heroLoading, setHeroLoading] = useState(true);

  const [movieSectionsData, setMovieSectionsData] = useState<Record<string, any[]>>({});
  const [cimaSeries, setCimaSeries] = useState<any[]>([]);
  const [recentMovies, setRecentMovies] = useState<any[]>([]);
  const [movieSectionsLoading, setMovieSectionsLoading] = useState(true);
  const [cimaSeriesLoading, setCimaSeriesLoading] = useState(true);
  const [recentMoviesLoading, setRecentMoviesLoading] = useState(true);

  // جلب محتوى متنوع للـ Hero (أفلام + مسلسلات + أنمي)
  useEffect(() => {
    let active = true;
    async function fetchHeroContent() {
      try {
        const [animeRes, movieRes, seriesRes] = await Promise.all([
          supabase.from('animes').select('*').eq('published', true).order('rating_average', { ascending: false }).limit(2),
          supabase.from('movies_cima').select('*').order('id', { ascending: false }).limit(2),
          supabase.from('tv_series').select('*').order('id', { ascending: false }).limit(1)
        ]);

        if (!active) return;

        const mixedHero = [
          ...(animeRes.data || []).map(a => ({ ...a, media_type: 'anime', cover_image_url: a.cover_image_url || a.banner_image_url })),
          ...(movieRes.data || []).map(mapCimaMovie),
          ...(seriesRes.data || []).map(mapCimaSeries),
        ];

        if (mixedHero.length > 0) {
          setHeroItems(mixedHero);
        }
      } catch (err) {
        console.error(err);
      } finally {
        if (active) setHeroLoading(false);
      }
    }

    fetchHeroContent();
    return () => { active = false; };
  }, []);

  // جلب أقسام الأفلام والمسلسلات من قاعدة البيانات
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      Promise.all(
        MOVIE_SECTIONS.map(async (sec) => {
          if (sec.key === 'ramadan-2026') {
            const { data } = await supabase
              .from('tv_series')
              .select('*')
              .eq('category_type', sec.category)
              .eq('year', sec.year)
              .limit(10)
              .order('id', { ascending: false });
            return [sec.key, (data || []).map(mapCimaSeries)] as const;
          } else {
            const { data } = await supabase
              .from('movies_cima')
              .select('*')
              .eq('category_type', sec.category)
              .eq('year', sec.year)
              .limit(10)
              .order('id', { ascending: false });
            return [sec.key, (data || []).map(mapCimaMovie)] as const;
          }
        })
      ).then((entries) => {
        if (!active) return;
        setMovieSectionsData(Object.fromEntries(entries));
        setMovieSectionsLoading(false);
      }).catch(() => {
        if (active) setMovieSectionsLoading(false);
      });

      // أحدث المسلسلات
      supabase
        .from('tv_series')
        .select('*')
        .limit(10)
        .order('id', { ascending: false })
        .then(({ data }) => {
          if (active && data) setCimaSeries(data.map(mapCimaSeries));
          if (active) setCimaSeriesLoading(false);
        }).catch(() => {
          if (active) setCimaSeriesLoading(false);
        });

      // أحدث الأفلام بشكل عام
      supabase
        .from('movies_cima')
        .select('*')
        .limit(10)
        .order('id', { ascending: false })
        .then(({ data }) => {
          if (active && data) setRecentMovies(data.map(mapCimaMovie));
          if (active) setRecentMoviesLoading(false);
        }).catch(() => {
          if (active) setRecentMoviesLoading(false);
        });
    }, 300);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  const { favoriteIds, toggleFavorite } = useFavorites();
  const { items: continueItems, loading: continueLoading } = useContinueWatching();

  useSEO({
    title: 'سيما سبيس CimaSpace — مشاهدة وتحميل الأفلام والمسلسلات والأنمي بجودة عالية',
    description: 'سيما سبيس CimaSpace - منصة المشاهدة الأولى عربياً. شاهد وتحميل أحدث الأفلام العربية والأجنبية والمسلسلات والأنمي المترجم والمدبلج بجودة عالية HD.',
    canonicalPath: '/',
  });

  const handleToggleFav = useCallback(
    (id: string, mediaType?: 'anime' | 'movie' | 'series') => {
      toggleFavorite(id, mediaType && mediaType !== 'anime' ? { mediaType } : undefined);
    },
    [toggleFavorite]
  );

  return (
    <div className="relative min-h-screen bg-[#07070A] text-white font-sans selection:bg-red-600 selection:text-white pb-32 dir-rtl overflow-x-hidden">
      
      <div className="absolute top-0 left-0 right-0 h-[500px] bg-gradient-to-b from-red-950/25 via-transparent to-transparent pointer-events-none blur-3xl z-0" />

      {heroLoading ? (
        <div className="relative h-[70vh] sm:h-[85vh] min-h-[460px] w-full bg-gradient-to-r from-[#121218] via-[#1a1a24] to-[#121218] animate-pulse" />
      ) : (
        <Hero animes={heroItems} />
      )}

      <div className="relative z-20 mt-4 sm:mt-6 space-y-6 sm:space-y-10 px-4 sm:px-8 lg:px-14 w-full max-w-full overflow-hidden">

        {continueItems && continueItems.length > 0 && (
          <ContinueWatchingSection items={continueItems} loading={continueLoading} />
        )}

        <div className="w-full py-1" style={hideScrollbarStyle}>
          <CategoryChips />
        </div>

        <RecommendedSection
          popularAnimes={popularAnimes}
          topRatedAnimes={topRatedAnimes}
          loading={popularAnimesLoading || topRatedAnimesLoading}
          favoriteIds={favoriteIds}
          onToggleFav={handleToggleFav}
        />

        <SwipeableSection
          title="أحدث الأفلام المضافة"
          icon={<Film className="h-5 w-5 sm:h-6 sm:w-6 text-red-500 fill-red-500/20" />}
          loading={recentMoviesLoading}
          animes={recentMovies}
          favoriteIds={favoriteIds}
          onToggleFav={handleToggleFav}
          viewMoreHref="/movies"
        />

        <Top10Section animes={popularAnimes} loading={popularAnimesLoading} />

        <SwipeableSection
          title="أحدث المسلسلات"
          icon={<Tv className="h-5 w-5 sm:h-6 sm:w-6 text-emerald-400" />}
          loading={cimaSeriesLoading}
          animes={cimaSeries}
          favoriteIds={favoriteIds}
          onToggleFav={handleToggleFav}
          viewMoreHref="/series"
        />

        <SwipeableSection
          title="أنمي أضيفت حديثاً"
          icon={<Sparkles className="h-5 w-5 sm:h-6 sm:w-6 text-red-500 fill-red-500/20" />}
          loading={recentAnimesLoading}
          animes={recentAnimes}
          favoriteIds={favoriteIds}
          onToggleFav={handleToggleFav}
        />

        {MOVIE_SECTIONS.map(sec => (
          <SwipeableSection
            key={sec.key}
            title={sec.label}
            icon={sec.icon}
            loading={movieSectionsLoading}
            animes={movieSectionsData[sec.key] || []}
            favoriteIds={favoriteIds}
            onToggleFav={handleToggleFav}
            viewMoreHref={sec.href}
          />
        ))}

        <SwipeableSection
          title="الأكثر مشاهدة وتداولاً"
          icon={<Flame className="h-5 w-5 sm:h-6 sm:w-6 text-amber-500 fill-amber-500/20" />}
          loading={popularAnimesLoading}
          animes={popularAnimes}
          favoriteIds={favoriteIds}
          onToggleFav={handleToggleFav}
        />

        <SwipeableSection
          title="الأعلى تقييماً وعالمياً"
          icon={<Star className="h-5 w-5 sm:h-6 sm:w-6 text-yellow-400 fill-yellow-400" />}
          loading={topRatedAnimesLoading}
          animes={topRatedAnimes}
          favoriteIds={favoriteIds}
          onToggleFav={handleToggleFav}
        />

      </div>
    </div>
  );
}

function ContinueWatchingSection({ items, loading }: { items: any[]; loading: boolean }) {
  const { navigate } = useRouter();
  if (loading) return <RowSkeletonSection title="متابعة المشاهدة" />;
  if (!items || items.length === 0) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-3 px-1">
        <div className="h-5 w-2 rounded-full bg-red-600" />
        <h2 className="text-lg sm:text-xl font-black text-white">متابعة المشاهدة</h2>
      </div>
      <div className="flex gap-3 sm:gap-4 pb-3 pt-1" style={hideScrollbarStyle}>
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => navigate(`/watch/${item.anime_id}/${item.episode_id}`)}
            className="group relative w-36 sm:w-48 md:w-56 shrink-0 cursor-pointer rounded-2xl bg-[#121219] border border-white/10 overflow-hidden"
          >
            <div className="relative aspect-[16/9] sm:aspect-[2/3] w-full overflow-hidden bg-zinc-950">
              <img
                src={item.animes?.cover_image_url || item.episodes?.thumbnail_url}
                alt=""
                loading="lazy"
                decoding="async"
                className="h-full w-full object-cover"
              />
            </div>
            <div className="p-2.5 space-y-1">
              <h3 className="truncate text-xs sm:text-sm font-bold text-gray-100">{item.animes?.title || 'محتوى'}</h3>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RecommendedSection({
  popularAnimes,
  topRatedAnimes,
  loading,
  favoriteIds,
  onToggleFav,
}: {
  popularAnimes: any[];
  topRatedAnimes: any[];
  loading: boolean;
  favoriteIds: Set<string>;
  onToggleFav: (id: string, mediaType?: 'anime' | 'movie' | 'series') => void;
}) {
  const { navigate } = useRouter();

  const recommended = Array.from(
    new Map(
      [...(topRatedAnimes || []), ...(popularAnimes || [])].map((item) => [item.id, item])
    ).values()
  ).slice(0, 10);

  if (loading) return <RowSkeletonSection title="مختارات لك" />;
  if (recommended.length === 0) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-xl bg-red-600/10 border border-red-500/20">
            <Sparkles className="h-5 w-5 sm:h-6 sm:w-6 text-red-400" />
          </div>
          <div>
            <h2 className="text-lg sm:text-xl font-black text-white">مختارات لك</h2>
            <p className="text-[11px] sm:text-xs text-gray-500 mt-0.5">
              أعمال تستحق المشاهدة
            </p>
          </div>
        </div>

        <button
          onClick={() => navigate('/anime-list')}
          className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-bold text-gray-200 hover:bg-red-600 hover:text-white transition-all"
        >
          المزيد
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
      </div>

      <div
        className="flex gap-3.5 sm:gap-4 pb-3 pt-1"
        style={hideScrollbarStyle}
      >
        {recommended.map((item: any) => (
          <div key={item.id} className="w-36 sm:w-48 md:w-56 shrink-0">
            <AnimeCard
              anime={item}
              favoriteIds={favoriteIds}
              onToggleFav={() => onToggleFav(item.id, item.media_type)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function Top10Section({ animes, loading }: { animes: any[]; loading: boolean }) {
  const { navigate } = useRouter();
  if (loading) return <RowSkeletonSection title="أفضل 10 أعمال اليوم" />;
  if (!animes || animes.length === 0) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2.5">
        <span className="text-xs sm:text-sm font-black text-white bg-red-600 px-2.5 py-1 rounded-lg">TOP 10</span>
        <h2 className="text-lg sm:text-xl font-extrabold text-white">الأكثر مشاهدة اليوم</h2>
      </div>
      <div className="flex gap-4 sm:gap-5 pb-3 pt-1" style={hideScrollbarStyle}>
        {animes.slice(0, 10).map((anime, index) => (
          <div
            key={anime.id}
            onClick={() => {
              if (anime.media_type === 'movie') navigate(`/movie/${anime.id}`);
              else if (anime.media_type === 'series') navigate(`/series/${anime.id}`);
              else navigate(`/anime/${anime.id}`);
            }}
            className="relative flex items-end cursor-pointer w-36 sm:w-48 md:w-56 shrink-0 group"
          >
            <span className="text-[90px] sm:text-[150px] font-black leading-none text-transparent select-none -mr-6 z-0" style={{ WebkitTextStroke: '2px rgba(255, 255, 255, 0.15)' }}>
              {index + 1}
            </span>
            <div className="w-32 sm:w-44 md:w-52 relative z-10 rounded-2xl overflow-hidden border border-white/10 bg-zinc-900 shrink-0">
              <img
                src={anime.cover_image_url || anime.banner_image_url}
                alt=""
                loading="lazy"
                decoding="async"
                className="aspect-[2/3] w-full object-cover"
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SwipeableSection({
  title,
  icon,
  loading,
  animes,
  favoriteIds,
  onToggleFav,
  viewMoreHref,
}: {
  title: string;
  icon?: React.ReactNode;
  loading: boolean;
  animes: any[];
  favoriteIds: Set<string>;
  onToggleFav: (id: string, mediaType?: 'anime' | 'movie' | 'series') => void;
  viewMoreHref?: string;
}) {
  const { navigate } = useRouter();
  const railRef = useRef<HTMLDivElement>(null);

  if (loading) return <RowSkeletonSection title={title} />;
  if (!animes || animes.length === 0) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-xl bg-white/5 border border-white/10">{icon}</div>
          <h2 className="text-lg sm:text-xl font-black text-white">{title}</h2>
        </div>
        {viewMoreHref && (
          <button
            onClick={() => navigate(viewMoreHref)}
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-3.5 py-1.5 text-xs font-bold text-gray-200 hover:bg-red-600 hover:text-white transition-all"
          >
            عرض الكل
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div ref={railRef} className="flex gap-3.5 sm:gap-4 pb-3 pt-1" style={{ ...hideScrollbarStyle, scrollBehavior: 'smooth' }}>
        {animes.map((a) => (
          <div key={a.id} className="w-36 sm:w-48 md:w-56 shrink-0">
            <AnimeCard anime={a} favoriteIds={favoriteIds} onToggleFav={() => onToggleFav(a.id, a.media_type)} />
          </div>
        ))}
      </div>
    </section>
  );
}

function RowSkeletonSection({ title }: { title: string }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2.5">
        <div className="h-5 w-2 rounded-full bg-red-600/30 animate-pulse" />
        <h2 className="text-lg sm:text-xl font-bold text-gray-600">{title}</h2>
      </div>
      <div className="flex gap-3.5 sm:gap-4 pb-3 pt-1" style={hideScrollbarStyle}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="w-36 sm:w-48 md:w-56 shrink-0">
            <CardSkeleton />
          </div>
        ))}
      </div>
    </div>
  );
}
